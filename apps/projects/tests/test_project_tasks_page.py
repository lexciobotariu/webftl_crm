import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.projects.models import ProjectTaskView, Status
from apps.tasks.factories import LabelFactory, TaskFactory

TOOLBAR = {'HTTP_HX_REQUEST': 'true', 'HTTP_HX_TRIGGER': 'task-toolbar'}
SEARCH = {'HTTP_HX_REQUEST': 'true', 'HTTP_HX_TRIGGER': 'task-search'}


def _member(project):
    user = UserFactory()
    ProjectAccessFactory(project=project, user=user)
    return user


def _url(project, query=''):
    base = reverse('project_tasks', args=[project.pk])
    return f'{base}?{query}' if query else base


def _titles(response):
    return [task.title for group in response.context['groups'] for task in group['rows']]


@pytest.mark.django_db
class TestAccess:
    def test_requires_login(self, client):
        project = ProjectFactory()
        assert client.get(_url(project)).status_code == 302

    def test_outsider_is_forbidden(self, client):
        project = ProjectFactory()
        client.force_login(UserFactory())
        assert client.get(_url(project)).status_code == 403

    def test_member_sees_the_tasks(self, client):
        project = ProjectFactory()
        user = _member(project)
        TaskFactory(project=project, title='Write the spec')
        client.force_login(user)
        response = client.get(_url(project, 'layout=list'))
        assert response.status_code == 200
        assert 'Write the spec' in response.content.decode()
        assert 'id="task-view"' in response.content.decode()
        assert 'id="task-toolbar"' in response.content.decode()

    def test_person_without_task_access_sees_no_tasks(self, client):
        project = ProjectFactory()
        preset = PermissionPreset.objects.create(
            name='Projects only', access_projects=True, access_tasks=False
        )
        user = UserFactory(permission_preset=preset)
        ProjectAccessFactory(project=project, user=user)
        TaskFactory(project=project, title='Hidden from them')
        client.force_login(user)
        response = client.get(_url(project, 'layout=list'))
        assert response.status_code == 200
        assert 'Hidden from them' not in response.content.decode()

    def test_project_nav_links_to_the_tasks_page(self, client):
        project = ProjectFactory()
        client.force_login(AdminUserFactory())
        html = client.get(reverse('project_detail', args=[project.pk])).content.decode()
        assert f'href="{_url(project)}"' in html


@pytest.mark.django_db
class TestFiltering:
    def test_hidden_status_leaves_the_list(self, client):
        project = ProjectFactory()
        user = _member(project)
        done = project.statuses.get(name='Done')
        TaskFactory(project=project, status=project.statuses.get(name='Backlog'), title='Keep')
        TaskFactory(project=project, status=done, title='Hide')
        client.force_login(user)
        response = client.get(_url(project, f'layout=list&hide_status={done.pk}'))
        assert _titles(response) == ['Keep']
        assert response.context['total_matching'] == 1
        assert response.context['total_visible'] == 2

    def test_status_added_later_shows_up_by_itself(self, client):
        project = ProjectFactory()
        user = _member(project)
        done = project.statuses.get(name='Done')
        added = Status.objects.create(project=project, name='QA', order=99)
        TaskFactory(project=project, status=added, title='In QA')
        client.force_login(user)
        response = client.get(_url(project, f'hide_status={done.pk}'))
        assert _titles(response) == ['In QA']

    def test_status_of_another_project_is_ignored(self, client):
        project = ProjectFactory()
        user = _member(project)
        foreign = ProjectFactory().statuses.first()
        TaskFactory(project=project, title='Still here')
        client.force_login(user)
        response = client.get(_url(project, f'hide_status={foreign.pk}'))
        assert _titles(response) == ['Still here']
        assert response.context['spec'].hidden_statuses == frozenset()

    def test_priority_assignee_label_and_search_filters(self, client):
        project = ProjectFactory()
        user = _member(project)
        bug = LabelFactory(project=project, name='bug')
        match = TaskFactory(
            project=project, assignee=user, priority='high', title='Login bug'
        )
        match.labels.add(bug)
        TaskFactory(project=project, assignee=user, priority='low', title='Login typo')
        TaskFactory(project=project, priority='high', title='Login other')
        client.force_login(user)
        query = f'priority=high&assignee={user.pk}&label={bug.pk}&q=login'
        assert _titles(client.get(_url(project, query))) == ['Login bug']

    def test_unknown_parameters_fall_back_to_the_default_view(self, client):
        project = ProjectFactory()
        user = _member(project)
        TaskFactory(project=project, title='Fine')
        client.force_login(user)
        response = client.get(_url(project, 'layout=x&group=x&sort=x&limit=x&priority=x'))
        assert response.status_code == 200
        assert _titles(response) == ['Fine']

    def test_filter_form_spelling_is_translated(self, client):
        project = ProjectFactory()
        user = _member(project)
        done = project.statuses.get(name='Done')
        shown = [s.pk for s in project.statuses.all() if s.pk != done.pk]
        TaskFactory(project=project, status=done, title='Done one')
        TaskFactory(project=project, status=project.statuses.get(name='Backlog'), title='Open one')
        client.force_login(user)
        query = 'filter=1&' + '&'.join(f'shown_status={pk}' for pk in shown)
        response = client.get(_url(project, query), **TOOLBAR)
        assert _titles(response) == ['Open one']
        assert response['HX-Push-Url'] == _url(project, f'layout=list&hide_status={done.pk}')

    def test_assignee_options_include_inactive_people_who_hold_tasks(self, client):
        project = ProjectFactory()
        user = _member(project)
        gone = UserFactory(name='Left Company', is_active=False)
        TaskFactory(project=project, assignee=gone)
        client.force_login(user)
        options = client.get(_url(project, 'layout=list')).context['assignee_options']
        assert 'Left Company' in [option['label'] for option in options]
        assert 'none' in [option['value'] for option in options]


@pytest.mark.django_db
class TestGroupingAndSorting:
    def test_groups_come_with_counts_from_every_matching_task(self, client):
        project = ProjectFactory()
        user = _member(project)
        backlog = project.statuses.get(name='Backlog')
        TaskFactory.create_batch(3, project=project, status=backlog)
        TaskFactory(project=project, status=project.statuses.get(name='Done'))
        client.force_login(user)
        groups = client.get(_url(project, 'layout=list&empty=0')).context['groups']
        assert [(g['label'], g['count']) for g in groups] == [('Backlog', 3), ('Done', 1)]

    def test_group_by_priority_and_no_grouping(self, client):
        project = ProjectFactory()
        user = _member(project)
        TaskFactory(project=project, priority='urgent', title='a')
        TaskFactory(project=project, priority='', title='b')
        client.force_login(user)
        by_priority = client.get(_url(project, 'group=priority')).context['groups']
        assert [g['label'] for g in by_priority] == ['Urgent', 'No priority']
        flat = client.get(_url(project, 'group=none')).context['groups']
        assert len(flat) == 1 and flat[0]['label'] is None

    def test_sort_choice_orders_rows(self, client):
        project = ProjectFactory()
        user = _member(project)
        for title in ('b task', 'a task', 'c task'):
            TaskFactory(project=project, title=title)
        client.force_login(user)
        response = client.get(_url(project, 'group=none&sort=title'))
        assert _titles(response) == ['a task', 'b task', 'c task']


@pytest.mark.django_db
class TestShowMore:
    def test_first_page_is_capped_and_show_more_raises_the_limit(self, client):
        project = ProjectFactory()
        user = _member(project)
        TaskFactory.create_batch(205, project=project)
        client.force_login(user)
        first = client.get(_url(project, 'group=none'))
        assert len(_titles(first)) == 200
        assert first.context['total_matching'] == 205
        assert first.context['more_url'] == _url(project, 'layout=list&group=none&limit=400')
        second = client.get(first.context['more_url'])
        assert len(_titles(second)) == 205
        assert second.context['more_url'] is None

    def test_no_show_more_when_everything_fits(self, client):
        project = ProjectFactory()
        user = _member(project)
        TaskFactory.create_batch(3, project=project)
        client.force_login(user)
        assert client.get(_url(project, 'layout=list')).context['more_url'] is None


@pytest.mark.django_db
class TestEmptyStates:
    def test_no_tasks_yet_offers_to_create_one(self, client):
        project = ProjectFactory()
        client.force_login(AdminUserFactory())
        html = client.get(_url(project, 'layout=list')).content.decode()
        assert 'No tasks yet' in html
        assert 'Create the first task' in html
        assert 'Nothing matches this filter' not in html

    def test_nothing_matching_the_filter_offers_clear_not_create(self, client):
        project = ProjectFactory()
        user = _member(project)
        done = project.statuses.get(name='Done')
        TaskFactory(project=project, status=done, title='Filtered out')
        client.force_login(user)
        html = client.get(_url(project, f'hide_status={done.pk}')).content.decode()
        assert 'Nothing matches this filter' in html
        assert 'Clear' in html
        assert 'No tasks yet' not in html
        assert 'Create the first task' not in html


@pytest.mark.django_db
class TestSavedView:
    def test_toolbar_request_saves_the_view(self, client):
        project = ProjectFactory()
        user = _member(project)
        done = project.statuses.get(name='Done')
        client.force_login(user)
        client.get(_url(project, f'layout=list&hide_status={done.pk}&group=assignee'), **TOOLBAR)
        saved = ProjectTaskView.objects.get(user=user, project=project)
        assert saved.params == {
            'layout': 'list', 'hide_status': [str(done.pk)], 'group': 'assignee',
        }

    def test_plain_get_does_not_save(self, client):
        project = ProjectFactory()
        user = _member(project)
        client.force_login(user)
        client.get(_url(project, 'layout=list&group=assignee'))
        assert not ProjectTaskView.objects.filter(user=user).exists()

    def test_refresh_and_search_requests_do_not_save(self, client):
        project = ProjectFactory()
        user = _member(project)
        client.force_login(user)
        client.get(_url(project, 'layout=list&group=assignee'), HTTP_HX_REQUEST='true')
        client.get(_url(project, 'layout=list&q=abc'), **SEARCH)
        assert not ProjectTaskView.objects.filter(user=user).exists()

    def test_search_text_and_paging_are_never_saved(self, client):
        project = ProjectFactory()
        user = _member(project)
        client.force_login(user)
        client.get(_url(project, 'layout=list&group=priority&q=abc&limit=400'), **TOOLBAR)
        saved = ProjectTaskView.objects.get(user=user, project=project)
        assert saved.params == {'layout': 'list', 'group': 'priority'}

    def test_bare_get_restores_the_saved_view_with_a_redirect(self, client):
        project = ProjectFactory()
        user = _member(project)
        ProjectTaskView.objects.create(
            user=user, project=project, params={'layout': 'list', 'group': 'assignee'}
        )
        client.force_login(user)
        response = client.get(_url(project))
        assert response.status_code == 302
        assert response['Location'] == _url(project, 'layout=list&group=assignee')

    def test_bare_get_without_a_saved_view_redirects_to_the_default(self, client):
        # The bare URL never renders, so browser history only ever holds URLs that
        # say what they showed; Back cannot land on "whatever is saved by now".
        project = ProjectFactory()
        client.force_login(_member(project))
        response = client.get(_url(project))
        assert response.status_code == 302
        assert response['Location'] == _url(project, 'layout=list')
        assert not ProjectTaskView.objects.filter(project=project).exists()

    def test_saved_view_is_revalidated_when_a_status_was_deleted(self, client):
        project = ProjectFactory()
        user = _member(project)
        review = project.statuses.get(name='Review')
        done = project.statuses.get(name='Done')
        ProjectTaskView.objects.create(
            user=user,
            project=project,
            params={'layout': 'list', 'hide_status': [str(review.pk), str(done.pk)]},
        )
        review.delete()
        client.force_login(user)
        response = client.get(_url(project))
        assert response['Location'] == _url(project, f'layout=list&hide_status={done.pk}')

    def test_saved_view_that_turns_out_to_be_the_default_is_dropped(self, client):
        project = ProjectFactory()
        user = _member(project)
        review = project.statuses.get(name='Review')
        ProjectTaskView.objects.create(
            user=user,
            project=project,
            params={'layout': 'list', 'hide_status': [str(review.pk)]},
        )
        review.delete()
        client.force_login(user)
        response = client.get(_url(project))
        assert response.status_code == 302
        assert response['Location'] == _url(project, 'layout=list')
        assert not ProjectTaskView.objects.filter(user=user, project=project).exists()

    def test_clearing_from_the_toolbar_removes_the_saved_view(self, client):
        project = ProjectFactory()
        user = _member(project)
        done = project.statuses.get(name='Done')
        ProjectTaskView.objects.create(
            user=user, project=project, params={'layout': 'list', 'hide_status': [str(done.pk)]}
        )
        client.force_login(user)
        client.get(_url(project, 'clear=1'), **TOOLBAR)
        assert not ProjectTaskView.objects.filter(user=user, project=project).exists()

    def test_a_shared_link_does_not_overwrite_my_saved_view(self, client):
        project = ProjectFactory()
        user = _member(project)
        ProjectTaskView.objects.create(
            user=user, project=project, params={'layout': 'list', 'group': 'assignee'}
        )
        client.force_login(user)
        response = client.get(_url(project, 'layout=list&group=priority'))
        assert response.status_code == 200
        assert ProjectTaskView.objects.get(user=user, project=project).params == {
            'layout': 'list', 'group': 'assignee',
        }

    def test_another_persons_saved_view_does_not_apply_to_me(self, client):
        project = ProjectFactory()
        owner = _member(project)
        other = _member(project)
        ProjectTaskView.objects.create(
            user=owner, project=project, params={'layout': 'list', 'group': 'assignee'}
        )
        client.force_login(other)
        assert client.get(_url(project, 'layout=list')).status_code == 200

    def test_one_row_per_person_and_project(self):
        project = ProjectFactory()
        user = _member(project)
        ProjectTaskView.objects.create(user=user, project=project, params={})
        with pytest.raises(IntegrityError), transaction.atomic():
            ProjectTaskView.objects.create(user=user, project=project, params={})

    def test_deleting_a_status_does_not_break_the_saved_view_row(self):
        project = ProjectFactory()
        user = _member(project)
        review = project.statuses.get(name='Review')
        ProjectTaskView.objects.create(
            user=user, project=project, params={'hide_status': [str(review.pk)]}
        )
        review.delete()
        assert ProjectTaskView.objects.filter(user=user, project=project).exists()


@pytest.mark.django_db
class TestUrlHeaders:
    def test_toolbar_request_pushes_the_canonical_url(self, client):
        project = ProjectFactory()
        client.force_login(_member(project))
        response = client.get(_url(project, 'group=assignee&sort=priority&dir=asc'), **TOOLBAR)
        assert response['HX-Push-Url'] == _url(project, 'layout=list&group=assignee')
        assert 'HX-Replace-Url' not in response

    def test_search_and_paging_replace_the_url_instead(self, client):
        project = ProjectFactory()
        client.force_login(_member(project))
        response = client.get(_url(project, 'q=abc'), **SEARCH)
        assert response['HX-Replace-Url'] == _url(project, 'layout=list&q=abc')
        assert 'HX-Push-Url' not in response

    def test_full_page_loads_carry_no_url_headers(self, client):
        project = ProjectFactory()
        client.force_login(_member(project))
        response = client.get(_url(project, 'layout=list'))
        assert 'HX-Push-Url' not in response
        assert 'HX-Replace-Url' not in response


@pytest.mark.django_db
class TestOverviewStaysIndependent:
    def test_overview_counts_ignore_the_tasks_page_filter(self, client):
        project = ProjectFactory()
        user = _member(project)
        done = project.statuses.get(name='Done')
        TaskFactory(project=project, status=project.statuses.get(name='Backlog'))
        TaskFactory(project=project, status=done)
        client.force_login(user)
        client.get(_url(project, f'hide_status={done.pk}'), **TOOLBAR)
        overview = client.get(reverse('project_detail', args=[project.pk]))
        assert overview.context['total_tasks'] == 2
        assert overview.context['completed_tasks'] == 1
        assert overview.context['active_tasks'] == 1
        assert overview.context['active_tab'] == 'overview'


@pytest.mark.django_db
class TestQueryCount:
    def test_rows_do_not_add_queries(self, client):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        project = ProjectFactory()
        user = _member(project)
        label = LabelFactory(project=project)
        client.force_login(user)
        client.get(_url(project, 'layout=list'))  # the first request creates one-off rows (company settings)

        def queries_for(n):
            for _ in range(n):
                task = TaskFactory(project=project, assignee=UserFactory())
                task.labels.add(label)
            with CaptureQueriesContext(connection) as captured:
                assert client.get(_url(project, 'layout=list')).status_code == 200
            return len(captured)

        few = queries_for(3)
        many = queries_for(30)
        assert many == few
