"""Services that create and change tasks without a form: the drawer and the MCP tools share them."""
from datetime import date

import pytest
from django.core.exceptions import PermissionDenied

from apps.accounts.factories import AdminUserFactory, UserFactory
from apps.projects.factories import ProjectAccessFactory, ProjectFactory
from apps.projects.models import Status
from apps.tasks import services
from apps.tasks.factories import LabelFactory, TaskFactory, TimeEntryFactory
from apps.tasks.models import Task, TaskActivity, TimeEntry


@pytest.fixture
def member_on_project():
    user = UserFactory()
    project = ProjectFactory()
    ProjectAccessFactory(project=project, user=user)
    return user, project


@pytest.mark.django_db
class TestCreateTask:
    def test_creates_in_first_board_column_with_activity(self, member_on_project):
        user, project = member_on_project
        label = LabelFactory(project=project)

        task = services.create_task(
            project, user, title='  Fix login  ', priority='high', billable=False,
            labels=[label], estimate_minutes=90, due_date=date(2026, 11, 1),
        )

        assert task.title == 'Fix login'
        assert task.status == project.statuses.filter(visible_on_board=True).first()
        assert task.number == 1
        assert not task.billable
        assert list(task.labels.all()) == [label]
        assert TaskActivity.objects.filter(task=task, activity_type='created', user=user).exists()

    def test_status_from_another_project_is_refused(self, member_on_project):
        user, project = member_on_project
        other = ProjectFactory().statuses.first()
        with pytest.raises(services.TaskValidationError):
            services.create_task(project, user, title='x', status=other)

    def test_label_from_another_project_is_refused(self, member_on_project):
        user, project = member_on_project
        with pytest.raises(services.TaskValidationError):
            services.create_task(project, user, title='x', labels=[LabelFactory()])
        assert not Task.objects.filter(project=project).exists()

    def test_assignee_must_be_on_the_project(self, member_on_project):
        user, project = member_on_project
        with pytest.raises(services.TaskValidationError):
            services.create_task(project, user, title='x', assignee=UserFactory())

    @pytest.mark.parametrize('title', ['', '   ', None])
    def test_title_is_required(self, member_on_project, title):
        user, project = member_on_project
        with pytest.raises(services.TaskValidationError):
            services.create_task(project, user, title=title)

    def test_unknown_priority_is_refused(self, member_on_project):
        user, project = member_on_project
        with pytest.raises(services.TaskValidationError):
            services.create_task(project, user, title='x', priority='asap')

    def test_needs_create_right(self):
        with pytest.raises(PermissionDenied):
            services.create_task(ProjectFactory(), UserFactory(), title='x')


@pytest.mark.django_db
class TestUpdateTask:
    def test_changes_several_fields_with_activity(self, member_on_project):
        user, project = member_on_project
        task = TaskFactory(project=project, billable=True, priority='low')
        TaskActivity.objects.filter(task=task).delete()

        services.update_task(task, user, billable=False, priority='urgent', assignee=user)

        task.refresh_from_db()
        assert (task.billable, task.priority, task.assignee) == (False, 'urgent', user)
        assert TaskActivity.objects.filter(task=task, activity_type='assignee_change').exists()

    def test_status_is_not_changed_here(self, member_on_project):
        user, project = member_on_project
        task = TaskFactory(project=project)
        with pytest.raises(services.TaskValidationError):
            services.update_task(task, user, status=project.statuses.last())

    def test_due_date_before_existing_start_is_refused(self, member_on_project):
        user, project = member_on_project
        task = TaskFactory(project=project, start_date=date(2026, 11, 10))
        with pytest.raises(services.TaskValidationError):
            services.update_task(task, user, due_date=date(2026, 11, 1))

    def test_needs_edit_right(self):
        with pytest.raises(PermissionDenied):
            services.update_task(TaskFactory(), UserFactory(), billable=False)


@pytest.mark.django_db
class TestLabels:
    def test_add_is_idempotent_and_logged_once(self, member_on_project):
        user, project = member_on_project
        task = TaskFactory(project=project)
        label = LabelFactory(project=project)

        assert services.add_label(task, label, user) is True
        assert services.add_label(task, label, user) is False

        assert list(task.labels.all()) == [label]
        assert TaskActivity.objects.filter(task=task, activity_type='label_added').count() == 1

    def test_remove_when_not_on_is_a_no_op(self, member_on_project):
        user, project = member_on_project
        task = TaskFactory(project=project)
        label = LabelFactory(project=project)
        assert services.remove_label(task, label, user) is False
        assert not TaskActivity.objects.filter(task=task, activity_type='label_removed').exists()

    def test_label_from_another_project_cannot_be_added(self, member_on_project):
        user, project = member_on_project
        task = TaskFactory(project=project)
        with pytest.raises(services.TaskValidationError):
            services.add_label(task, LabelFactory(), user)

    def test_toggle_still_toggles(self, member_on_project):
        user, project = member_on_project
        task = TaskFactory(project=project)
        label = LabelFactory(project=project)
        services.toggle_label(task, label, user)
        assert task.labels.filter(pk=label.pk).exists()
        services.toggle_label(task, label, user)
        assert not task.labels.filter(pk=label.pk).exists()


@pytest.mark.django_db
class TestCreateLabel:
    def test_admin_creates_label(self):
        project = ProjectFactory()
        label = services.create_label(project, AdminUserFactory(), ' Bug ', '#ff0000')
        assert (label.project, label.name, label.color) == (project, 'Bug', '#ff0000')

    def test_duplicate_name_in_any_case_is_refused(self):
        project = ProjectFactory()
        LabelFactory(project=project, name='Bug')
        with pytest.raises(services.TaskValidationError):
            services.create_label(project, AdminUserFactory(), 'bug')

    def test_bad_color_is_refused(self):
        with pytest.raises(services.TaskValidationError):
            services.create_label(ProjectFactory(), AdminUserFactory(), 'Bug', 'red')

    def test_task_editor_without_project_edit_cannot(self, member_on_project):
        user, project = member_on_project
        with pytest.raises(PermissionDenied):
            services.create_label(project, user, 'Bug')


@pytest.mark.django_db
class TestFindTask:
    def test_finds_by_identifier_in_any_case(self, member_on_project):
        user, project = member_on_project
        task = TaskFactory(project=project)
        assert services.find_task(user, f' {project.key.lower()}-{task.number} ') == task

    def test_task_the_person_cannot_see_looks_missing(self):
        task = TaskFactory()
        with pytest.raises(Task.DoesNotExist):
            services.find_task(UserFactory(), task.identifier)

    @pytest.mark.parametrize('identifier', ['', 'CUST', '12', 'CUST-', 'CUST-x', None])
    def test_malformed_identifier(self, identifier):
        with pytest.raises(Task.DoesNotExist):
            services.find_task(AdminUserFactory(), identifier)


@pytest.mark.django_db
class TestStartAndFinishWork:
    def test_start_takes_moves_and_starts_timer(self, member_on_project):
        user, project = member_on_project
        task = TaskFactory(project=project, status=project.statuses.get(name='To Do'))
        other = TimeEntryFactory(user=user, running=True, task=TaskFactory(project=project))

        entry = services.start_work(task, user)

        task.refresh_from_db()
        assert task.assignee == user
        assert task.status.name == 'In Progress'
        assert entry.task == task and entry.ended_at is None
        other.refresh_from_db()
        assert other.ended_at is not None

    def test_start_keeps_someone_elses_assignment_and_started_column(self, member_on_project):
        user, project = member_on_project
        colleague = UserFactory()
        ProjectAccessFactory(project=project, user=colleague)
        review = project.statuses.get(name='Review')
        task = TaskFactory(project=project, status=review, assignee=colleague)

        services.start_work(task, user)

        task.refresh_from_db()
        assert task.assignee == colleague
        assert task.status == review

    def test_finish_stops_timer_and_moves_to_done(self, member_on_project):
        user, project = member_on_project
        task = TaskFactory(project=project)
        services.start_work(task, user)

        entry = services.finish_work(task, user)

        task.refresh_from_db()
        assert task.status.category == Status.COMPLETED
        assert entry is not None and entry.ended_at is not None
        assert not TimeEntry.objects.filter(user=user, ended_at__isnull=True).exists()

    def test_finish_leaves_a_timer_on_another_task(self, member_on_project):
        user, project = member_on_project
        task = TaskFactory(project=project)
        running = TimeEntryFactory(user=user, running=True, task=TaskFactory(project=project))

        assert services.finish_work(task, user) is None
        running.refresh_from_db()
        assert running.ended_at is None

    def test_needs_edit_right(self):
        with pytest.raises(PermissionDenied):
            services.start_work(TaskFactory(), UserFactory())
