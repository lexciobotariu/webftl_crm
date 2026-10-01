import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.tasks.factories import LabelFactory, TaskActivityFactory, TaskFactory
from apps.tasks.models import TaskActivity


def _editor(project, **flags):
    preset = PermissionPreset.objects.create(
        name=f'editor{PermissionPreset.objects.count()}',
        access_projects=True, access_tasks=True, tasks_edit_own=True, **flags,
    )
    user = UserFactory(permission_preset=preset)
    ProjectAccessFactory(project=project, user=user)
    return user


def _viewer(project):
    preset = PermissionPreset.objects.create(
        name=f'viewer{PermissionPreset.objects.count()}', access_projects=True, access_tasks=True,
    )
    user = UserFactory(permission_preset=preset)
    ProjectAccessFactory(project=project, user=user)
    return user


def _comment(task, user, content='original'):
    return TaskActivityFactory(task=task, user=user, activity_type='comment', content=content)


def _edit_url(comment):
    return reverse('comment_edit', args=[comment.task_id, comment.pk])


def _delete_url(comment):
    return reverse('comment_delete', args=[comment.task_id, comment.pk])


@pytest.mark.django_db
class TestEditComment:
    def test_the_author_edits_their_comment(self, client):
        task = TaskFactory()
        author = _editor(task.project)
        comment = _comment(task, author)
        client.force_login(author)

        response = client.post(_edit_url(comment), {'content': 'changed **now**'})

        assert response.status_code == 200
        comment.refresh_from_db()
        assert comment.content == 'changed **now**'
        assert comment.edited_at is not None
        html = response.content.decode()
        assert f'id="activity-{comment.pk}"' in html
        assert '<strong>now</strong>' in html
        assert 'edited' in html

    def test_the_edit_form_comes_back_with_the_text(self, client):
        task = TaskFactory()
        author = _editor(task.project)
        comment = _comment(task, author, content='first draft')
        client.force_login(author)

        html = client.get(_edit_url(comment)).content.decode()

        assert f'id="activity-{comment.pk}"' in html
        assert 'first draft</textarea>' in html
        assert 'role="tablist"' in html

    def test_cancel_returns_the_comment_unchanged(self, client):
        task = TaskFactory()
        author = _editor(task.project)
        comment = _comment(task, author, content='keep me')
        client.force_login(author)

        html = client.get(_edit_url(comment) + '?cancel=1').content.decode()

        assert 'keep me' in html and '<textarea' not in html

    def test_someone_else_cannot_edit_it(self, client):
        task = TaskFactory()
        comment = _comment(task, _editor(task.project))
        client.force_login(_editor(task.project))

        assert client.post(_edit_url(comment), {'content': 'hijack'}).status_code == 403
        assert client.get(_edit_url(comment)).status_code == 403
        comment.refresh_from_db()
        assert comment.content == 'original'

    def test_the_author_who_lost_edit_rights_cannot_edit_it(self, client):
        task = TaskFactory()
        author = _editor(task.project)
        comment = _comment(task, author)
        author.project_access.all().delete()
        client.force_login(author)

        assert client.post(_edit_url(comment), {'content': 'late'}).status_code == 403

    def test_an_admin_edits_anyones_comment(self, client):
        task = TaskFactory()
        comment = _comment(task, _editor(task.project))
        client.force_login(AdminUserFactory())

        assert client.post(_edit_url(comment), {'content': 'moderated'}).status_code == 200
        comment.refresh_from_db()
        assert comment.content == 'moderated'

    def test_tasks_edit_all_is_not_enough_for_someone_elses_comment(self, client):
        task = TaskFactory()
        comment = _comment(task, _editor(task.project))
        client.force_login(_editor(task.project, tasks_edit_all=True))

        assert client.post(_edit_url(comment), {'content': 'x'}).status_code == 403

    def test_empty_or_too_long_text_is_refused(self, client):
        from apps.tasks.templatetags.task_markdown import MAX_LENGTH

        task = TaskFactory()
        author = _editor(task.project)
        comment = _comment(task, author)
        client.force_login(author)

        assert client.post(_edit_url(comment), {'content': '   '}).status_code == 400
        assert client.post(_edit_url(comment), {'content': 'x' * (MAX_LENGTH + 1)}).status_code == 400
        comment.refresh_from_db()
        assert comment.content == 'original'

    def test_only_comments_of_that_task_can_be_edited(self, client):
        task = TaskFactory()
        author = _editor(task.project)
        other_task = TaskFactory(project=task.project)
        comment = _comment(other_task, author)
        change = TaskActivityFactory(task=task, user=author, activity_type='status_change', content='x')
        client.force_login(author)

        wrong_task = reverse('comment_edit', args=[task.pk, comment.pk])
        not_a_comment = reverse('comment_edit', args=[task.pk, change.pk])
        assert client.post(wrong_task, {'content': 'y'}).status_code == 404
        assert client.post(not_a_comment, {'content': 'y'}).status_code == 404


@pytest.mark.django_db
class TestDeleteComment:
    def test_the_author_deletes_their_comment(self, client):
        task = TaskFactory()
        author = _editor(task.project)
        comment = _comment(task, author)
        client.force_login(author)

        response = client.post(_delete_url(comment))

        assert response.status_code == 200
        assert response.content == b''
        assert not TaskActivity.objects.filter(pk=comment.pk).exists()

    def test_someone_else_cannot_delete_it_but_an_admin_can(self, client):
        task = TaskFactory()
        comment = _comment(task, _editor(task.project))

        client.force_login(_editor(task.project))
        assert client.post(_delete_url(comment)).status_code == 403
        assert TaskActivity.objects.filter(pk=comment.pk).exists()

        client.force_login(AdminUserFactory())
        assert client.post(_delete_url(comment)).status_code == 200
        assert not TaskActivity.objects.filter(pk=comment.pk).exists()

    def test_it_needs_post(self, client):
        task = TaskFactory()
        author = _editor(task.project)
        comment = _comment(task, author)
        client.force_login(author)

        assert client.get(_delete_url(comment)).status_code == 405

    def test_other_activity_cannot_be_deleted(self, client):
        task = TaskFactory()
        change = TaskActivityFactory(task=task, activity_type='status_change', content='x')
        client.force_login(AdminUserFactory())

        assert client.post(reverse('comment_delete', args=[task.pk, change.pk])).status_code == 404


@pytest.mark.django_db
class TestCommentControls:
    def test_controls_show_only_on_comments_you_may_change(self, client):
        task = TaskFactory()
        author = _editor(task.project)
        mine = _comment(task, author, content='mine')
        theirs = _comment(task, _editor(task.project), content='theirs')
        client.force_login(author)

        html = client.get(reverse('task_activity_list', args=[task.pk])).content.decode()

        assert _edit_url(mine) in html and _delete_url(mine) in html
        assert _edit_url(theirs) not in html and _delete_url(theirs) not in html

    def test_a_viewer_sees_no_controls(self, client):
        task = TaskFactory()
        viewer = _viewer(task.project)
        _comment(task, viewer)
        client.force_login(viewer)

        response = client.get(reverse('task_activity_list', args=[task.pk]))

        assert response.status_code == 200
        html = response.content.decode()
        assert 'original' in html
        assert '/edit/' not in html

    def test_a_new_comment_comes_with_its_controls(self, client):
        task = TaskFactory()
        author = _editor(task.project)
        client.force_login(author)

        html = client.post(reverse('comment_create', args=[task.pk]), {'content': 'hi'}).content.decode()

        comment = task.activities.get(activity_type='comment')
        assert f'id="activity-{comment.pk}"' in html
        assert _edit_url(comment) in html

    def test_the_activity_list_does_not_query_per_comment(self, client):
        task = TaskFactory()
        admin = AdminUserFactory()
        client.force_login(admin)
        url = reverse('task_activity_list', args=[task.pk])
        _comment(task, UserFactory())
        client.get(url)

        with CaptureQueriesContext(connection) as one:
            client.get(url)
        for _ in range(5):
            _comment(task, UserFactory())
        with CaptureQueriesContext(connection) as six:
            client.get(url)

        assert len(six) == len(one)


@pytest.mark.django_db
class TestMoreActivity:
    def _admin_client(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        return admin

    def test_a_title_change_is_logged_and_cut_to_fit(self, client):
        task = TaskFactory(title='Old title')
        self._admin_client(client)

        response = client.post(reverse('task_edit_title', args=[task.pk]), {'title': 'N' * 600})

        row = task.activities.get(activity_type='title_change')
        assert row.old_value == 'Old title'
        assert len(row.new_value) == 255
        assert 'activityUpdated' in response['HX-Trigger']

    def test_a_description_change_is_logged_without_a_diff(self, client):
        task = TaskFactory(description='before')
        self._admin_client(client)

        response = client.post(reverse('task_edit_description', args=[task.pk]), {'description': 'after'})

        row = task.activities.get(activity_type='description_change')
        assert row.content == 'updated the description'
        assert row.old_value == '' and row.new_value == ''
        assert 'activityUpdated' in response['HX-Trigger']

    def test_saving_the_same_description_logs_nothing(self, client):
        task = TaskFactory(description='same')
        self._admin_client(client)

        client.post(reverse('task_edit_description', args=[task.pk]), {'description': 'same'})

        assert not task.activities.filter(activity_type='description_change').exists()

    def test_an_estimate_change_is_logged(self, client):
        task = TaskFactory(time_estimate=None)
        self._admin_client(client)

        response = client.post(reverse('task_update_estimate', args=[task.pk]), {'time_estimate': '4'})
        client.post(reverse('task_update_estimate', args=[task.pk]), {'time_estimate': ''})

        rows = list(task.activities.filter(activity_type='estimate_change').order_by('pk'))
        assert [(r.old_value, r.new_value) for r in rows] == [('', '4h'), ('4h', '')]
        assert rows[0].content == 'set the estimate to 4h'
        assert rows[1].content == 'removed the estimate'
        assert 'activityUpdated' in response['HX-Trigger']

    def test_toggling_a_label_is_logged_both_ways(self, client):
        task = TaskFactory()
        label = LabelFactory(project=task.project, name='bug')
        admin = self._admin_client(client)
        url = reverse('task_toggle_label', args=[task.pk, label.pk])

        response = client.post(url)
        client.post(url)

        rows = list(task.activities.filter(activity_type__in=['label_added', 'label_removed']).order_by('pk'))
        assert [(r.activity_type, r.new_value or r.old_value, r.user) for r in rows] == [
            ('label_added', 'bug', admin), ('label_removed', 'bug', admin),
        ]
        assert 'activityUpdated' in response['HX-Trigger']

    def test_label_changes_from_the_edit_form_are_logged(self, client):
        project = ProjectFactory()
        keep, drop, add = (LabelFactory(project=project, name=n) for n in ('keep', 'drop', 'add'))
        task = TaskFactory(project=project, title='T')
        task.labels.set([keep, drop])
        self._admin_client(client)

        client.post(reverse('task_edit', args=[task.pk]), {
            'title': 'T', 'description': task.description, 'priority': task.priority,
            'labels': [keep.pk, add.pk],
        })

        added = list(task.activities.filter(activity_type='label_added').values_list('new_value', flat=True))
        removed = list(task.activities.filter(activity_type='label_removed').values_list('old_value', flat=True))
        assert added == ['add'] and removed == ['drop']

    def test_the_new_rows_render_in_the_drawer(self, client):
        task = TaskFactory(title='Old', description='a', time_estimate=None)
        self._admin_client(client)
        client.post(reverse('task_edit_title', args=[task.pk]), {'title': 'New'})
        client.post(reverse('task_edit_description', args=[task.pk]), {'description': 'b'})
        client.post(reverse('task_update_estimate', args=[task.pk]), {'time_estimate': '3'})

        html = client.get(reverse('task_activity_list', args=[task.pk])).content.decode()

        assert 'changed the title to New' in html
        assert 'updated the description' in html
        assert 'set the estimate to 3h' in html


@pytest.mark.django_db
class TestReviewFixes:
    def test_saving_an_unchanged_comment_does_not_mark_it_edited(self, client):
        task = TaskFactory()
        author = _editor(task.project)
        comment = _comment(task, author, content='same')
        client.force_login(author)

        html = client.post(_edit_url(comment), {'content': 'same'}).content.decode()

        comment.refresh_from_db()
        assert comment.edited_at is None
        assert 'edited' not in html

    def test_the_list_does_not_refresh_over_an_open_comment_editor(self, client):
        task = TaskFactory()
        client.force_login(AdminUserFactory())

        html = client.get(reverse('task_detail', args=[task.pk])).content.decode()

        assert (
            f"activityUpdated[!document.querySelector('#activity-items-{task.pk} form')] from:body"
        ) in html

    def test_an_author_reading_their_comments_costs_the_same_queries_for_one_or_six(self, client):
        task = TaskFactory()
        author = _editor(task.project)
        client.force_login(author)
        url = reverse('task_activity_list', args=[task.pk])
        _comment(task, author)
        client.get(url)

        with CaptureQueriesContext(connection) as one:
            client.get(url)
        for _ in range(5):
            _comment(task, author)
        with CaptureQueriesContext(connection) as six:
            client.get(url)

        assert len(six) == len(one)

    @pytest.mark.parametrize('page', ['drawer', 'full page'])
    def test_the_drawer_and_full_page_load_activity_once(self, client, page):
        task = TaskFactory()
        client.force_login(AdminUserFactory())
        for _ in range(3):
            _comment(task, UserFactory())
        url = (
            reverse('task_detail', args=[task.pk]) if page == 'drawer'
            else reverse('task_full_page', args=[task.project_id, task.pk])
        )

        with CaptureQueriesContext(connection) as queries:
            client.get(url)

        activity_reads = [q['sql'] for q in queries if 'FROM "tasks_taskactivity"' in q['sql']]
        assert len(activity_reads) == 1, activity_reads
