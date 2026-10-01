import threading

import pytest
from django.db import connection
from django.urls import reverse

from apps.accounts.factories import AdminUserFactory
from apps.projects.factories import ProjectFactory
from apps.projects.keys import derive_key
from apps.projects.models import Project
from apps.tasks.factories import TaskFactory
from apps.tasks.models import Task


class TestDeriveKey:
    @pytest.mark.parametrize('name, key', [
        ('Custom CRM', 'CUST'),
        ('erp', 'ERP'),
        ('ÉLAN Studio', 'ELAN'),
        ('R&D lab', 'RDLA'),
        ('My W', 'MYW'),
        ('3D Print', 'DPRI'),
        ('Q', 'QX'),
        ('9 Q', 'QX'),
    ])
    def test_takes_the_first_letters_and_digits_of_the_name(self, name, key):
        assert derive_key(name, set()) == key

    def test_a_name_without_letters_falls_back_to_the_pk(self):
        assert derive_key('2024', set(), pk=17) == 'P17'
        assert derive_key('—', set(), pk=3) == 'P3'

    def test_a_name_without_letters_and_no_pk_still_gets_a_key(self):
        assert derive_key('2024', set()) == 'PX'

    def test_a_taken_key_gets_a_numeric_suffix(self):
        assert derive_key('Custom CRM', {'CUST'}) == 'CUST2'
        assert derive_key('Custom CRM', {'CUST', 'CUST2'}) == 'CUST3'

    def test_the_suffix_keeps_going_past_nine_within_six_characters(self):
        taken = {'CUST'} | {f'CUST{n}' for n in range(2, 100)}
        key = derive_key('Custom CRM', taken)
        assert key == 'CUS100'
        assert len(key) <= 6

    def test_every_key_is_valid(self):
        for name in ('a', 'Z9', 'x' * 300, '!!!', '123abc', 'Ñandú'):
            key = derive_key(name, set(), pk=5)
            assert 2 <= len(key) <= 6
            assert key[0].isalpha() and key.isalnum() and key == key.upper()


@pytest.mark.django_db
class TestProjectKey:
    def test_a_new_project_gets_a_key_from_its_name(self):
        assert ProjectFactory(name='Custom CRM').key == 'CUST'

    def test_a_given_key_is_kept(self):
        assert ProjectFactory(name='Custom CRM', key='CRM').key == 'CRM'

    def test_a_second_project_with_the_same_name_gets_a_suffix(self):
        ProjectFactory(name='Website')
        assert ProjectFactory(name='Website').key == 'WEBS2'

    def test_renaming_does_not_change_the_key(self):
        project = ProjectFactory(name='Custom CRM')
        project.name = 'Something else'
        project.save()
        project.refresh_from_db()
        assert project.key == 'CUST'


@pytest.mark.django_db
class TestTaskNumbers:
    def test_numbers_count_up_per_project(self):
        alpha = ProjectFactory(name='Alpha')
        beta = ProjectFactory(name='Beta')
        a1, a2 = TaskFactory(project=alpha), TaskFactory(project=alpha)
        b1 = TaskFactory(project=beta)
        a3 = TaskFactory(project=alpha)

        assert [a1.number, a2.number, a3.number] == [1, 2, 3]
        assert b1.number == 1
        assert a3.identifier == 'ALPH-3'
        assert b1.identifier == 'BETA-1'

    def test_saving_a_task_again_keeps_its_number(self):
        task = TaskFactory()
        task.title = 'Changed'
        task.save()
        task.refresh_from_db()
        assert task.number == 1

    def test_a_deleted_task_does_not_free_its_number(self):
        project = ProjectFactory()
        TaskFactory(project=project)
        TaskFactory(project=project).delete()
        assert TaskFactory(project=project).number == 3

    def test_a_full_project_save_does_not_reset_the_counter(self):
        project = ProjectFactory()
        stale = Project.objects.get(pk=project.pk)
        TaskFactory(project=project)
        TaskFactory(project=project)

        stale.name = 'Renamed'
        stale.save()

        assert Project.objects.get(pk=project.pk).task_counter == 2
        assert TaskFactory(project=project).number == 3


@pytest.mark.race
@pytest.mark.django_db(transaction=True)
def test_concurrent_creates_in_one_project_get_distinct_numbers():
    project = ProjectFactory()
    status = project.statuses.first()
    errors = []
    barrier = threading.Barrier(6)

    def create(i):
        try:
            barrier.wait()
            Task.objects.create(project=project, status=status, title=f'T{i}')
        except Exception as exc:  # pragma: no cover - surfaced by the assert below
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=create, args=(i,)) for i in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    numbers = sorted(Task.objects.filter(project=project).values_list('number', flat=True))
    assert numbers == [1, 2, 3, 4, 5, 6]
    assert Project.objects.get(pk=project.pk).task_counter == 6


@pytest.mark.django_db
class TestKeyInSettings:
    def _post(self, client, project, **data):
        payload = {'name': project.name, 'description': '', 'github_repo_url': ''}
        payload.update(data)
        return client.post(reverse('project_settings_update', args=[project.pk]), payload)

    def test_the_form_shows_the_key(self, client):
        project = ProjectFactory(key='CUST')
        client.force_login(AdminUserFactory())

        content = self._post(client, project).content.decode()

        assert 'name="key"' in content and 'value="CUST"' in content

    def test_a_new_key_is_saved_in_capitals_and_ids_follow(self, client):
        project = ProjectFactory(key='CUST')
        task = TaskFactory(project=project)
        client.force_login(AdminUserFactory())

        response = self._post(client, project, key=' crm2 ')

        assert 'Settings saved' in response.content.decode()
        project.refresh_from_db()
        assert project.key == 'CRM2'
        task.refresh_from_db()
        assert task.identifier == 'CRM2-1'

    @pytest.mark.parametrize('key', ['', 'A', '1ABC', 'TOOLONGX', 'AB-C', 'ÄBC'])
    def test_an_invalid_key_is_refused(self, client, key):
        project = ProjectFactory(key='CUST')
        client.force_login(AdminUserFactory())

        content = self._post(client, project, key=key).content.decode()

        assert 'Settings saved' not in content
        assert '2 to 6' in content
        project.refresh_from_db()
        assert project.key == 'CUST'

    def test_a_key_another_project_uses_is_refused(self, client):
        ProjectFactory(key='TAKEN')
        project = ProjectFactory(key='CUST', name='Mine')
        client.force_login(AdminUserFactory())

        content = self._post(client, project, key='taken', name='Renamed').content.decode()

        assert 'already used' in content
        project.refresh_from_db()
        assert (project.key, project.name) == ('CUST', 'Mine')

    def test_saving_settings_without_a_key_field_keeps_the_key(self, client):
        project = ProjectFactory(key='CUST')
        client.force_login(AdminUserFactory())

        client.post(reverse('project_settings_update', args=[project.pk]), {'name': 'Renamed'})

        project.refresh_from_db()
        assert (project.key, project.name) == ('CUST', 'Renamed')

    def test_saving_settings_does_not_touch_the_counter(self, client):
        project = ProjectFactory()
        client.force_login(AdminUserFactory())
        TaskFactory(project=project)
        TaskFactory(project=project)

        self._post(client, project, key='NEW')

        assert Project.objects.get(pk=project.pk).task_counter == 2


@pytest.mark.django_db
class TestAdmin:
    def test_number_and_counter_are_read_only(self, client):
        admin_user = AdminUserFactory(is_staff=True, is_superuser=True)
        task = TaskFactory()
        client.force_login(admin_user)

        task_page = client.get(reverse('admin:tasks_task_change', args=[task.pk])).content.decode()
        project_page = client.get(reverse('admin:projects_project_change', args=[task.project.pk])).content.decode()

        assert 'name="number"' not in task_page and 'field-number' in task_page
        assert 'name="task_counter"' not in project_page and 'field-task_counter' in project_page
        assert 'name="key"' in project_page


@pytest.mark.django_db
class TestIdsOnPages:
    def test_the_list_drawer_full_page_and_create_drawer_show_the_new_id(self, client):
        project = ProjectFactory(name='Custom CRM', key='CUST')
        admin_user = AdminUserFactory()
        TaskFactory(project=project)
        task = TaskFactory(project=project, assignee=admin_user)
        client.force_login(admin_user)

        pages = {
            'list': client.get(reverse('my_tasks'), follow=True),
            'drawer': client.get(reverse('task_detail', args=[task.pk])),
            'full page': client.get(reverse('task_full_page', args=[project.pk, task.pk])),
        }
        for page, response in pages.items():
            html = response.content.decode()
            assert 'CUST-2' in html, page

        create = client.get(reverse('task_create', args=[project.pk]), HTTP_HX_REQUEST='true').content.decode()
        assert '>CUST</span>' in create


@pytest.mark.django_db
class TestReviewFixes:
    def test_a_project_keyed_task_keeps_old_hash_task_references_on_the_pk(self):
        from apps.integrations.github import find_referenced_task

        project = ProjectFactory(name='Tasks', key='TASK')
        by_pk = TaskFactory(project=project, id=10**6)
        # Another task on the project whose number is that pk.
        Project.objects.filter(pk=project.pk).update(task_counter=10**6 - 1)
        by_number = TaskFactory(project=project)
        assert by_number.number == by_pk.pk

        assert find_referenced_task(f'#TASK-{by_pk.pk}', project) == by_pk
        assert find_referenced_task(f'fixes TASK-{by_number.number}', project) == by_number

    def test_the_admin_cannot_move_a_task_to_another_project(self, client):
        admin_user = AdminUserFactory(is_staff=True, is_superuser=True)
        task = TaskFactory()
        client.force_login(admin_user)

        page = client.get(reverse('admin:tasks_task_change', args=[task.pk])).content.decode()
        add_page = client.get(reverse('admin:tasks_task_add')).content.decode()

        assert 'name="project"' not in page
        assert 'name="project"' in add_page

    def test_a_key_error_keeps_the_other_edits(self, client):
        ProjectFactory(key='TAKEN')
        project = ProjectFactory(key='CUST', name='Mine')
        client.force_login(AdminUserFactory())

        content = client.post(reverse('project_settings_update', args=[project.pk]), {
            'name': 'New name', 'description': 'New description',
            'github_repo_url': 'https://github.com/o/r', 'key': 'taken',
        }).content.decode()

        assert 'value="New name"' in content
        assert 'New description</textarea>' in content
        assert 'value="https://github.com/o/r"' in content

    def test_the_settings_page_shows_the_key_field(self, client):
        project = ProjectFactory(key='CUST')
        client.force_login(AdminUserFactory())

        content = client.get(reverse('project_settings', args=[project.pk])).content.decode()

        assert 'name="key"' in content and 'value="CUST"' in content
