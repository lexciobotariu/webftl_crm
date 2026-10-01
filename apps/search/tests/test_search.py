import re
from itertools import count

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.accounts.permissions import PermissionPreset
from apps.clients.factories import ClientFactory
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.search import services
from apps.search.pages import PAGES, pages_for
from apps.tasks.factories import TaskFactory

_names = count()


def _user(**flags):
    """A person whose preset has exactly these flags on top of "everything off"."""
    base = {
        'access_dashboard': False, 'access_clients': False, 'access_projects': False,
        'access_tasks': False, 'access_todos': False, 'access_notes': False,
        'access_salaries': False, 'access_invoices': False, 'access_team': False,
    }
    base.update(flags)
    return UserFactory(permission_preset=PermissionPreset.objects.create(name=f'p{next(_names)}', **base))


def _member(**flags):
    return _user(access_projects=True, access_tasks=True, access_clients=True, **flags)


@pytest.mark.django_db
class TestTasks:
    def test_matches_the_title_case_insensitively(self):
        user = _member()
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        TaskFactory(project=project, title='Fix The Login Bug')
        TaskFactory(project=project, title='Something else')

        results = services.search(user, 'login')

        assert [t.title for t in results.tasks] == ['Fix The Login Bug']

    def test_only_tasks_the_person_may_see(self):
        user = _member()
        mine, theirs = ProjectFactory(), ProjectFactory()
        ProjectAccessFactory(project=mine, user=user)
        TaskFactory(project=mine, title='shared secret in mine')
        TaskFactory(project=theirs, title='shared secret in theirs')

        assert [t.title for t in services.search(user, 'shared secret').tasks] == ['shared secret in mine']

    def test_view_all_sees_every_project(self):
        user = _member(tasks_view_all=True)
        TaskFactory(title='shared secret anywhere')

        assert len(services.search(user, 'shared secret').tasks) == 1

    def test_no_tasks_module_means_no_task_section(self):
        user = _user(access_projects=True, access_clients=True)
        project = ProjectFactory()
        ProjectAccessFactory(project=project, user=user)
        TaskFactory(project=project, title='Fix login')

        assert services.search(user, 'login').tasks == []

    def test_a_key_and_number_find_that_task_of_that_project(self):
        user = _member()
        alpha = ProjectFactory(name='Alpha', key='ALPH')
        beta = ProjectFactory(name='Beta', key='BETA')
        for project in (alpha, beta):
            ProjectAccessFactory(project=project, user=user)
        TaskFactory.create_batch(11, project=alpha)
        TaskFactory.create_batch(12, project=beta)
        target = TaskFactory(project=alpha, title='Unrelated title')
        assert target.number == 12
        TaskFactory(project=alpha, title='Mentions ALPH-12')

        for query in ('ALPH-12', 'alph-12', 'Alph-12'):
            tasks = services.search(user, query).tasks
            assert tasks[0] == target, query
            assert beta.tasks.get(number=12) not in tasks, query

    def test_a_plain_number_finds_that_number_in_every_visible_project(self):
        user = _member()
        alpha = ProjectFactory(name='Alpha')
        beta = ProjectFactory(name='Beta')
        hidden = ProjectFactory(name='Hidden')
        for project in (alpha, beta):
            ProjectAccessFactory(project=project, user=user)
        for project in (alpha, beta, hidden):
            TaskFactory.create_batch(12, project=project)

        tasks = services.search(user, '12').tasks

        assert {(t.project_id, t.number) for t in tasks} == {(alpha.pk, 12), (beta.pk, 12)}

    def test_an_unknown_key_or_the_old_name_prefix_finds_nothing(self):
        user = _member()
        project = ProjectFactory(name='My Website', key='WEB')
        ProjectAccessFactory(project=project, user=user)
        TaskFactory.create_batch(12, project=project)

        for query in ('ZZZ-12', 'MY W-12', 'WEBX-12'):
            assert services.search(user, query).tasks == [], query

    def test_a_single_digit_is_a_task_number_and_nothing_else(self):
        user = _member()
        project = ProjectFactory(name='Project 7')
        ProjectAccessFactory(project=project, user=user)
        TaskFactory.create_batch(6, project=project)
        target = TaskFactory(project=project, title='Seventh')
        TaskFactory(project=project, title='Has a 7 in the title')

        results = services.search(user, '7')

        assert not results.too_short
        assert results.tasks == [target]
        # One character is still too little to match names by.
        assert results.projects == [] and results.clients == [] and results.pages == []
        assert services.search(user, 'a').too_short

    def test_an_id_does_not_match_a_task_you_cannot_see(self):
        user = _member()
        hidden = TaskFactory()

        assert services.search(user, hidden.identifier).tasks == []

    def test_a_huge_number_does_not_break_the_query(self):
        user = _member()

        assert services.search(user, '9' * 40).tasks == []
        assert services.search(user, 'X-' + '9' * 40).tasks == []

    def test_percent_and_underscore_are_literal(self):
        user = _member(tasks_view_all=True)
        TaskFactory(title='100% done')
        TaskFactory(title='anything at all')

        assert [t.title for t in services.search(user, '0% d').tasks] == ['100% done']
        assert services.search(user, '__').tasks == []

    def test_five_per_section_newest_first(self):
        user = _member(tasks_view_all=True)
        for number in range(8):
            TaskFactory(title=f'needle {number}')

        tasks = services.search(user, 'needle').tasks

        assert len(tasks) == 5
        assert tasks[0].title == 'needle 7'


@pytest.mark.django_db
class TestProjectsAndClients:
    def test_projects_follow_visibility(self):
        user = _member()
        mine, theirs = ProjectFactory(name='Alpha mine'), ProjectFactory(name='Alpha theirs')
        ProjectAccessFactory(project=mine, user=user)

        assert [p.name for p in services.search(user, 'alpha').projects] == ['Alpha mine']

        everyone = _member(projects_view_all=True)
        assert {p.pk for p in services.search(everyone, 'alpha').projects} == {mine.pk, theirs.pk}

    def test_no_projects_module_means_no_project_section(self):
        user = _user(access_tasks=True, access_clients=True, projects_view_all=True)
        ProjectFactory(name='Alpha')

        assert services.search(user, 'alpha').projects == []

    def test_clients_follow_visibility_and_the_module(self):
        user = _member()
        own = ClientFactory(name='Acme own', created_by=user)
        ClientFactory(name='Acme other')

        assert [c.pk for c in services.search(user, 'acme').clients] == [own.pk]

        everyone = _member(clients_view_all=True)
        assert len(services.search(everyone, 'acme').clients) == 2

        without = _user(access_projects=True, access_tasks=True, clients_view_all=True)
        assert services.search(without, 'acme').clients == []

    def test_a_user_without_the_clients_module_sees_no_client_names_in_the_view(self, client):
        user = _user(access_projects=True, access_tasks=True, access_dashboard=True, clients_view_all=True)
        ClientFactory(name='Confidential Corp')
        client.force_login(user)

        response = client.get(reverse('search'), {'q': 'confidential'})

        assert 'Confidential Corp' not in response.content.decode()

    def test_five_per_section(self):
        user = _member(projects_view_all=True, clients_view_all=True)
        for number in range(7):
            ProjectFactory(name=f'zeta project {number}')
            ClientFactory(name=f'zeta client {number}')

        results = services.search(user, 'zeta')

        assert len(results.projects) == 5
        assert len(results.clients) == 5


@pytest.mark.django_db
class TestQuery:
    def test_under_two_characters_is_too_short(self):
        user = _member(tasks_view_all=True)
        TaskFactory(title='a b c')

        for query in ('', ' ', 'a', ' a ', None):
            results = services.search(user, query)
            assert results.too_short
            assert results.empty

    def test_the_query_is_cut_to_the_shared_limit(self):
        from apps.tasks.viewspec import MAX_QUERY_LENGTH

        user = _member(tasks_view_all=True)
        TaskFactory(title='x' * MAX_QUERY_LENGTH)

        results = services.search(user, 'x' * (MAX_QUERY_LENGTH + 500))

        assert len(results.query) == MAX_QUERY_LENGTH
        assert len(results.tasks) == 1


@pytest.mark.django_db
class TestPages:
    def test_matching_pages_are_listed_for_those_who_can_open_them(self):
        admin = AdminUserFactory()
        member = _user(access_dashboard=True, access_tasks=True)

        assert 'Settings' in [p.label for p in services.search(admin, 'sett').pages]
        assert services.search(member, 'sett').pages == []
        assert [p.label for p in services.search(member, 'my ').pages] == ['My Tasks', 'My Week']

    def test_the_page_list_is_the_sidebars_for_several_kinds_of_user(self, client):
        users = [
            AdminUserFactory(),
            UserFactory(),
            _user(),
            _user(access_dashboard=True),
            _user(access_clients=True, access_projects=True),
            _user(access_tasks=True, access_team=True),
            _user(access_salaries=True, access_invoices=True),
        ]
        for user in users:
            client.force_login(user)
            html = client.get(reverse('changelog')).content.decode()
            sidebar = re.search(r'<aside.*?</aside>', html, re.S).group(0)
            in_sidebar = set(re.findall(r'href="([^"]+)"', sidebar))
            assert in_sidebar == {page.url for page in pages_for(user)}, user.email

    def test_every_page_has_a_route(self):
        for page in PAGES:
            assert page.url.startswith('/')


@pytest.mark.django_db
class TestView:
    def test_it_needs_a_login(self, client):
        response = client.get(reverse('search'), {'q': 'abc'})

        assert response.status_code == 302
        assert '/accounts/login/' in response['Location']

    def test_results_are_real_links_and_tasks_carry_their_drawer_url(self, client):
        user = _member()
        project = ProjectFactory(name='Custom CRM')
        ProjectAccessFactory(project=project, user=user)
        task = TaskFactory(project=project, title='Palette target')
        client.force_login(user)

        content = client.get(reverse('search'), {'q': 'palette'}).content.decode()

        assert f'href="{reverse("task_full_page", args=[project.pk, task.pk])}"' in content
        assert f'data-detail-url="{reverse("task_detail", args=[task.pk])}"' in content
        assert '>CUST-1<' in content
        assert 'role="option"' in content
        assert '<html' not in content

    def test_the_query_is_escaped(self, client):
        client.force_login(_member())

        content = client.get(reverse('search'), {'q': '<script>alert(1)</script>'}).content.decode()

        assert '<script>' not in content
        assert '&lt;script&gt;' in content

    def test_it_says_when_there_is_nothing(self, client):
        client.force_login(_member())

        assert 'Nothing found' in client.get(reverse('search'), {'q': 'zzzzzz'}).content.decode()
        assert 'at least 2 characters' in client.get(reverse('search'), {'q': 'z'}).content.decode()

    def test_a_request_costs_a_handful_of_queries_not_the_context_processors(self, client):
        user = _member(tasks_view_all=True, projects_view_all=True, clients_view_all=True)
        for number in range(5):
            TaskFactory(title=f'needle {number}')
        client.force_login(user)
        client.get(reverse('search'), {'q': 'needle'})  # warm per-process caches

        with CaptureQueriesContext(connection) as ctx:
            client.get(reverse('search'), {'q': 'needle'})

        # session + user + preset, then tasks, projects, clients. The context
        # processors (permissions, timers, theme) would add more.
        assert len(ctx) <= 8, [q['sql'][:80] for q in ctx.captured_queries]


@pytest.mark.django_db
class TestPaletteMarkup:
    def test_the_palette_and_the_sidebar_button_are_on_every_page(self, client):
        client.force_login(_member())

        html = client.get(reverse('changelog')).content.decode()

        assert 'id="palette"' in html
        assert 'role="combobox"' in html
        assert 'hx-sync="this:replace"' in html
        assert 'hx-indicator="#palette-spinner"' in html
        assert 'window.openPalette' in html

    def test_logged_out_pages_have_no_palette(self, client):
        html = client.get(reverse('account_login')).content.decode()

        assert 'id="palette"' not in html
