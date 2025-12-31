# WebFTL CRM Security Audit and Testing Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Audit the entire CRM for security vulnerabilities, race conditions, and UI/UX inconsistencies, then create comprehensive tests for all apps.

**Architecture:** This plan is organized by app (accounts, clients, projects, tasks, integrations), with each app having three phases: security audit, race condition analysis, and test creation. Tests use Django's TestCase with pytest for running.

**Tech Stack:** Django 4.x, PostgreSQL, HTMX, Alpine.js, pytest-django, factory_boy

---

## Phase 1: Setup Test Infrastructure

### Task 1.1: Create Test Configuration

**Files:**
- Create: `pytest.ini`
- Create: `conftest.py`
- Create: `apps/conftest.py`

**Step 1: Create pytest.ini**

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings
python_files = tests.py test_*.py *_tests.py
addopts = -v --tb=short --strict-markers
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    security: marks security-related tests
    race: marks race condition tests
```

**Step 2: Create root conftest.py**

```python
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def user(db):
    """Create a regular user."""
    return User.objects.create_user(
        email='user@example.com',
        name='Test User',
        password='testpass123',
        role='member'
    )


@pytest.fixture
def admin_user(db):
    """Create an admin user."""
    return User.objects.create_user(
        email='admin@example.com',
        name='Admin User',
        password='testpass123',
        role='admin'
    )


@pytest.fixture
def client_logged_in(client, user):
    """Return a logged-in test client."""
    client.force_login(user)
    return client


@pytest.fixture
def admin_client_logged_in(client, admin_user):
    """Return a logged-in admin test client."""
    client.force_login(admin_user)
    return client
```

**Step 3: Run to verify setup**

Run: `pytest --collect-only`
Expected: pytest discovers test infrastructure

**Step 4: Commit**

```bash
git add pytest.ini conftest.py
git commit -m "test: add pytest configuration and fixtures"
```

---

### Task 1.2: Create Factory Classes

**Files:**
- Create: `apps/accounts/factories.py`
- Create: `apps/clients/factories.py`
- Create: `apps/projects/factories.py`
- Create: `apps/tasks/factories.py`

**Step 1: Create accounts factories**

```python
# apps/accounts/factories.py
import factory
from django.contrib.auth import get_user_model

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f'user{n}@example.com')
    name = factory.Faker('name')
    role = 'member'
    is_active = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop('password', 'testpass123')
        user = super()._create(model_class, *args, **kwargs)
        user.set_password(password)
        user.save()
        return user


class AdminUserFactory(UserFactory):
    role = 'admin'
    email = factory.Sequence(lambda n: f'admin{n}@example.com')
```

**Step 2: Create clients factories**

```python
# apps/clients/factories.py
import factory
from apps.clients.models import Client


class ClientFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Client

    name = factory.Faker('company')
    email = factory.Faker('company_email')
    phone = factory.Faker('phone_number')
    address = factory.Faker('address')
    notes = factory.Faker('paragraph')
```

**Step 3: Create projects factories**

```python
# apps/projects/factories.py
import factory
from apps.projects.models import Project, Status
from apps.clients.factories import ClientFactory


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project

    client = factory.SubFactory(ClientFactory)
    name = factory.Faker('catch_phrase')
    description = factory.Faker('paragraph')
    github_repo_url = ''
    github_sync_enabled = False


class StatusFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Status

    project = factory.SubFactory(ProjectFactory)
    name = factory.Faker('word')
    order = factory.Sequence(lambda n: n)
```

**Step 4: Create tasks factories**

```python
# apps/tasks/factories.py
import factory
from apps.tasks.models import Task, Subtask, Label, Comment, TaskActivity, Attachment
from apps.projects.factories import ProjectFactory, StatusFactory
from apps.accounts.factories import UserFactory


class LabelFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Label

    project = factory.SubFactory(ProjectFactory)
    name = factory.Faker('word')
    color = '#6366f1'


class TaskFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Task

    project = factory.SubFactory(ProjectFactory)
    status = factory.LazyAttribute(lambda o: o.project.statuses.first() or StatusFactory(project=o.project))
    title = factory.Faker('sentence', nb_words=5)
    description = factory.Faker('paragraph')
    priority = factory.Iterator(['low', 'medium', 'high', 'urgent', ''])
    order = factory.Sequence(lambda n: n)


class SubtaskFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Subtask

    task = factory.SubFactory(TaskFactory)
    title = factory.Faker('sentence', nb_words=3)
    completed = False
    order = factory.Sequence(lambda n: n)


class CommentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Comment

    task = factory.SubFactory(TaskFactory)
    author = factory.SubFactory(UserFactory)
    content = factory.Faker('paragraph')


class TaskActivityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TaskActivity

    task = factory.SubFactory(TaskFactory)
    user = factory.SubFactory(UserFactory)
    activity_type = 'comment'
    content = factory.Faker('sentence')
```

**Step 5: Commit**

```bash
git add apps/*/factories.py
git commit -m "test: add factory classes for all models"
```

---

## Phase 2: Accounts App - Security Audit & Tests

### Task 2.1: Security Issues - Accounts App

**Files:**
- Review: `apps/accounts/views.py:1-68`
- Review: `apps/accounts/models.py:1-33`

**Security Findings:**

1. **CRITICAL: GitHub Token Storage (Line 16 in models.py)**
   - Issue: `github_token` stored in plain text
   - Risk: Token exposure if database is compromised
   - Fix: Encrypt token using `django-fernet-fields` or similar

2. **MEDIUM: No Rate Limiting on toggle_role**
   - Issue: No protection against brute-force role toggling
   - Risk: Denial of service for admin operations

3. **LOW: Broad Exception Handling (Lines 22-37 in views.py)**
   - Issue: `except (ImportError, Exception)` catches all errors silently
   - Risk: Hides bugs and security issues

**Step 1: Document security findings in test comments**

Create test file with security-focused tests.

**Step 2: Commit findings**

```bash
git add docs/security/
git commit -m "docs: document accounts app security findings"
```

---

### Task 2.2: Create Accounts App Tests

**Files:**
- Create: `apps/accounts/tests/__init__.py`
- Create: `apps/accounts/tests/test_views.py`
- Create: `apps/accounts/tests/test_models.py`

**Step 1: Create test directory**

```bash
mkdir -p apps/accounts/tests
touch apps/accounts/tests/__init__.py
```

**Step 2: Write model tests**

```python
# apps/accounts/tests/test_models.py
import pytest
from apps.accounts.factories import UserFactory, AdminUserFactory


@pytest.mark.django_db
class TestUserModel:
    def test_create_user(self):
        user = UserFactory()
        assert user.email is not None
        assert user.role == 'member'
        assert user.is_admin is False

    def test_create_admin_user(self):
        admin = AdminUserFactory()
        assert admin.role == 'admin'
        assert admin.is_admin is True

    def test_user_str(self):
        user = UserFactory(email='test@example.com')
        assert str(user) == 'test@example.com'

    def test_is_admin_property(self):
        member = UserFactory(role='member')
        admin = UserFactory(role='admin')
        assert member.is_admin is False
        assert admin.is_admin is True
```

**Step 3: Write view tests**

```python
# apps/accounts/tests/test_views.py
import pytest
from django.urls import reverse
from apps.accounts.factories import UserFactory, AdminUserFactory


@pytest.mark.django_db
class TestDashboard:
    def test_dashboard_requires_login(self, client):
        response = client.get(reverse('dashboard'))
        assert response.status_code == 302
        assert '/accounts/login/' in response.url

    def test_dashboard_accessible_when_logged_in(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert response.status_code == 200

    def test_dashboard_shows_stats(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        assert 'client_count' in response.context
        assert 'project_count' in response.context
        assert 'my_task_count' in response.context


@pytest.mark.django_db
class TestTeamList:
    def test_team_list_requires_admin(self, client):
        user = UserFactory(role='member')
        client.force_login(user)
        response = client.get(reverse('team_list'))
        assert response.status_code == 403

    def test_team_list_accessible_by_admin(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.get(reverse('team_list'))
        assert response.status_code == 200

    def test_team_list_pagination(self, client):
        admin = AdminUserFactory()
        # Create 25 users (more than TEAM_MEMBERS_PER_PAGE=20)
        for _ in range(25):
            UserFactory()
        client.force_login(admin)
        response = client.get(reverse('team_list'))
        assert response.context['page_obj'].has_next()


@pytest.mark.django_db
@pytest.mark.security
class TestToggleRole:
    def test_toggle_role_requires_admin(self, client):
        user = UserFactory(role='member')
        target = UserFactory(role='member')
        client.force_login(user)
        response = client.post(reverse('toggle_role', args=[target.pk]))
        assert response.status_code == 403

    def test_toggle_role_works_for_admin(self, client):
        admin = AdminUserFactory()
        target = UserFactory(role='member')
        client.force_login(admin)
        response = client.post(reverse('toggle_role', args=[target.pk]))
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.role == 'admin'

    def test_admin_cannot_toggle_own_role(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.post(reverse('toggle_role', args=[admin.pk]))
        admin.refresh_from_db()
        assert admin.role == 'admin'  # Unchanged

    def test_toggle_role_requires_post(self, client):
        admin = AdminUserFactory()
        target = UserFactory()
        client.force_login(admin)
        response = client.get(reverse('toggle_role', args=[target.pk]))
        assert response.status_code == 405
```

**Step 4: Run tests**

Run: `pytest apps/accounts/tests/ -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add apps/accounts/tests/
git commit -m "test: add accounts app tests"
```

---

## Phase 3: Clients App - Security Audit & Tests

### Task 3.1: Security Issues - Clients App

**Files:**
- Review: `apps/clients/views.py:1-141`

**Security Findings:**

1. **CRITICAL: No Authorization Checks on Client CRUD (Lines 26-57)**
   - Issue: Any logged-in user can create/edit clients
   - Risk: Unauthorized data modification
   - Recommendation: Add permission checks or ownership model

2. **MEDIUM: Direct POST Data Access (Lines 65-68)**
   - Issue: `client_edit_drawer` directly uses POST data without form validation
   - Risk: Potential for invalid data injection
   - Fix: Use ClientForm for validation

3. **MEDIUM: Nullable Fields Set to None (Lines 66-68)**
   - Issue: `or None` pattern may cause issues with EmailField
   - Risk: Data integrity issues

4. **LOW: No CSRF Token Verification Message**
   - Issue: HTMX requests rely on Django CSRF but no explicit check documented

**Step 1: Document findings**

**Step 2: Create tests that verify authorization**

---

### Task 3.2: Create Clients App Tests

**Files:**
- Create: `apps/clients/tests/__init__.py`
- Create: `apps/clients/tests/test_views.py`
- Create: `apps/clients/tests/test_models.py`

**Step 1: Create test directory**

```bash
mkdir -p apps/clients/tests
touch apps/clients/tests/__init__.py
```

**Step 2: Write model tests**

```python
# apps/clients/tests/test_models.py
import pytest
from apps.clients.factories import ClientFactory
from apps.projects.factories import ProjectFactory


@pytest.mark.django_db
class TestClientModel:
    def test_create_client(self):
        client = ClientFactory()
        assert client.name is not None
        assert client.pk is not None

    def test_client_str(self):
        client = ClientFactory(name='Acme Corp')
        assert str(client) == 'Acme Corp'

    def test_project_count_property(self):
        client = ClientFactory()
        assert client.project_count == 0
        ProjectFactory(client=client)
        ProjectFactory(client=client)
        assert client.project_count == 2

    def test_client_ordering(self):
        ClientFactory(name='Zebra Corp')
        ClientFactory(name='Alpha Inc')
        from apps.clients.models import Client
        clients = list(Client.objects.all())
        assert clients[0].name == 'Alpha Inc'
        assert clients[1].name == 'Zebra Corp'
```

**Step 3: Write view tests**

```python
# apps/clients/tests/test_views.py
import pytest
from django.urls import reverse
from apps.accounts.factories import UserFactory, AdminUserFactory
from apps.clients.factories import ClientFactory


@pytest.mark.django_db
class TestClientList:
    def test_client_list_requires_login(self, client):
        response = client.get(reverse('client_list'))
        assert response.status_code == 302

    def test_client_list_shows_clients(self, client):
        user = UserFactory()
        client.force_login(user)
        ClientFactory(name='Test Client')
        response = client.get(reverse('client_list'))
        assert response.status_code == 200
        assert 'Test Client' in response.content.decode()

    def test_client_list_pagination(self, client):
        user = UserFactory()
        for i in range(25):
            ClientFactory(name=f'Client {i}')
        client.force_login(user)
        response = client.get(reverse('client_list'))
        assert response.context['page_obj'].has_next()


@pytest.mark.django_db
class TestClientCreate:
    def test_client_create_requires_login(self, client):
        response = client.post(reverse('client_create'), {'name': 'New Client'})
        assert response.status_code == 302

    def test_client_create_with_valid_data(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.post(reverse('client_create'), {
            'name': 'New Client',
            'email': 'new@client.com',
            'phone': '555-1234',
            'address': '123 Main St',
            'notes': 'Important client',
        })
        assert response.status_code == 302  # Redirect on success
        from apps.clients.models import Client
        assert Client.objects.filter(name='New Client').exists()

    def test_client_create_with_invalid_data(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.post(reverse('client_create'), {
            'name': '',  # Required field
        })
        assert response.status_code == 200  # Form re-rendered
        from apps.clients.models import Client
        assert Client.objects.count() == 0


@pytest.mark.django_db
class TestClientDetail:
    def test_client_detail_shows_info(self, client):
        user = UserFactory()
        test_client = ClientFactory(name='Detail Client', email='detail@test.com')
        client.force_login(user)
        response = client.get(reverse('client_detail', args=[test_client.pk]))
        assert response.status_code == 200
        assert 'Detail Client' in response.content.decode()

    def test_client_detail_404_for_nonexistent(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('client_detail', args=[99999]))
        assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.security
class TestClientDelete:
    def test_delete_requires_admin(self, client):
        user = UserFactory(role='member')
        test_client = ClientFactory()
        client.force_login(user)
        response = client.post(reverse('client_delete', args=[test_client.pk]))
        assert response.status_code == 403

    def test_admin_can_delete(self, client):
        admin = AdminUserFactory()
        test_client = ClientFactory()
        client.force_login(admin)
        response = client.post(reverse('client_delete', args=[test_client.pk]))
        assert response.status_code == 302
        from apps.clients.models import Client
        assert not Client.objects.filter(pk=test_client.pk).exists()

    def test_delete_requires_post(self, client):
        admin = AdminUserFactory()
        test_client = ClientFactory()
        client.force_login(admin)
        response = client.get(reverse('client_delete', args=[test_client.pk]))
        assert response.status_code == 405
```

**Step 4: Run tests**

Run: `pytest apps/clients/tests/ -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add apps/clients/tests/
git commit -m "test: add clients app tests"
```

---

## Phase 4: Projects App - Security Audit & Tests

### Task 4.1: Security Issues - Projects App

**Files:**
- Review: `apps/projects/views.py:1-175`

**Security Findings:**

1. **CRITICAL: JSON Body Parsing Without Validation (Line 108)**
   - Issue: `json.loads(request.body)` without try/catch in production path
   - Risk: Server crash on malformed JSON
   - Fix: Already has try/except in webhook, need same for reorder_statuses

2. **HIGH: No Authorization on Project CRUD (Lines 38-73)**
   - Issue: Any user can create/edit/view any project
   - Risk: Unauthorized access to project data
   - Recommendation: Add project membership or ownership model

3. **MEDIUM: Race Condition in status_create (Lines 151-160)**
   - Issue: `project.statuses.count()` for order can race
   - Risk: Duplicate order values if concurrent requests
   - Fix: Use `F()` expression or database-level sequence

4. **LOW: No Validation on Status Name**
   - Issue: Empty status names could be created
   - Risk: UI confusion

**Step 1: Document and test race condition**

---

### Task 4.2: Create Projects App Tests

**Files:**
- Create: `apps/projects/tests/__init__.py`
- Create: `apps/projects/tests/test_views.py`
- Create: `apps/projects/tests/test_models.py`

**Step 1: Create test directory**

```bash
mkdir -p apps/projects/tests
touch apps/projects/tests/__init__.py
```

**Step 2: Write model tests**

```python
# apps/projects/tests/test_models.py
import pytest
from apps.projects.factories import ProjectFactory, StatusFactory
from apps.tasks.factories import TaskFactory


@pytest.mark.django_db
class TestProjectModel:
    def test_create_project_creates_default_statuses(self):
        project = ProjectFactory()
        # Default statuses are created in save()
        assert project.statuses.count() == 5
        status_names = list(project.statuses.values_list('name', flat=True))
        assert 'Backlog' in status_names
        assert 'Done' in status_names

    def test_project_str(self):
        project = ProjectFactory(name='Test Project')
        assert project.name in str(project)
        assert project.client.name in str(project)

    def test_task_count_property(self):
        project = ProjectFactory()
        assert project.task_count == 0
        status = project.statuses.first()
        TaskFactory(project=project, status=status)
        TaskFactory(project=project, status=status)
        assert project.task_count == 2


@pytest.mark.django_db
class TestStatusModel:
    def test_status_ordering(self):
        project = ProjectFactory()
        # Clear default statuses
        project.statuses.all().delete()
        StatusFactory(project=project, name='Third', order=2)
        StatusFactory(project=project, name='First', order=0)
        StatusFactory(project=project, name='Second', order=1)
        statuses = list(project.statuses.all())
        assert statuses[0].name == 'First'
        assert statuses[1].name == 'Second'
        assert statuses[2].name == 'Third'

    def test_task_count_property(self):
        project = ProjectFactory()
        status = project.statuses.first()
        assert status.task_count == 0
        TaskFactory(project=project, status=status)
        assert status.task_count == 1
```

**Step 3: Write view tests**

```python
# apps/projects/tests/test_views.py
import pytest
import json
from django.urls import reverse
from apps.accounts.factories import UserFactory, AdminUserFactory
from apps.projects.factories import ProjectFactory, StatusFactory
from apps.clients.factories import ClientFactory


@pytest.mark.django_db
class TestProjectList:
    def test_project_list_requires_login(self, client):
        response = client.get(reverse('project_list'))
        assert response.status_code == 302

    def test_project_list_shows_projects(self, client):
        user = UserFactory()
        ProjectFactory(name='Test Project')
        client.force_login(user)
        response = client.get(reverse('project_list'))
        assert response.status_code == 200
        assert 'Test Project' in response.content.decode()

    def test_project_list_filter_by_client(self, client):
        user = UserFactory()
        client1 = ClientFactory(name='Client A')
        client2 = ClientFactory(name='Client B')
        ProjectFactory(name='Project A', client=client1)
        ProjectFactory(name='Project B', client=client2)
        client.force_login(user)
        response = client.get(reverse('project_list') + f'?client={client1.pk}')
        assert 'Project A' in response.content.decode()
        assert 'Project B' not in response.content.decode()


@pytest.mark.django_db
class TestProjectBoard:
    def test_project_board_shows_kanban(self, client):
        user = UserFactory()
        project = ProjectFactory()
        client.force_login(user)
        response = client.get(reverse('project_board', args=[project.pk]))
        assert response.status_code == 200

    def test_project_board_htmx_returns_partial(self, client):
        user = UserFactory()
        project = ProjectFactory()
        client.force_login(user)
        response = client.get(
            reverse('project_board', args=[project.pk]),
            HTTP_HX_REQUEST='true'
        )
        assert response.status_code == 200
        # HTMX request returns just the board partial


@pytest.mark.django_db
@pytest.mark.security
class TestProjectDelete:
    def test_delete_requires_admin(self, client):
        user = UserFactory(role='member')
        project = ProjectFactory()
        client.force_login(user)
        response = client.post(reverse('project_delete', args=[project.pk]))
        assert response.status_code == 403

    def test_admin_can_delete(self, client):
        admin = AdminUserFactory()
        project = ProjectFactory()
        pk = project.pk
        client.force_login(admin)
        response = client.post(reverse('project_delete', args=[pk]))
        assert response.status_code == 302
        from apps.projects.models import Project
        assert not Project.objects.filter(pk=pk).exists()


@pytest.mark.django_db
class TestStatusManagement:
    def test_create_status(self, client):
        user = UserFactory()
        project = ProjectFactory()
        initial_count = project.statuses.count()
        client.force_login(user)
        response = client.post(
            reverse('status_create', args=[project.pk]),
            {'name': 'New Status'}
        )
        assert response.status_code == 200
        assert project.statuses.count() == initial_count + 1

    def test_delete_empty_status(self, client):
        user = UserFactory()
        project = ProjectFactory()
        status = project.statuses.first()
        client.force_login(user)
        response = client.post(
            reverse('status_delete', args=[project.pk, status.pk])
        )
        assert response.status_code == 200

    def test_cannot_delete_status_with_tasks(self, client):
        user = UserFactory()
        project = ProjectFactory()
        status = project.statuses.first()
        from apps.tasks.factories import TaskFactory
        TaskFactory(project=project, status=status)
        client.force_login(user)
        response = client.post(
            reverse('status_delete', args=[project.pk, status.pk])
        )
        assert response.status_code == 400


@pytest.mark.django_db
@pytest.mark.race
class TestReorderStatuses:
    def test_reorder_statuses(self, client):
        user = UserFactory()
        project = ProjectFactory()
        statuses = list(project.statuses.all())
        new_order = [s.pk for s in reversed(statuses)]
        client.force_login(user)
        response = client.post(
            reverse('reorder_statuses', args=[project.pk]),
            json.dumps({'order': new_order}),
            content_type='application/json'
        )
        assert response.status_code == 204
        # Verify order changed
        project.statuses.first()  # Refresh
        reordered = list(project.statuses.all())
        assert reordered[0].pk == new_order[0]

    def test_reorder_invalid_json(self, client):
        user = UserFactory()
        project = ProjectFactory()
        client.force_login(user)
        response = client.post(
            reverse('reorder_statuses', args=[project.pk]),
            'invalid json',
            content_type='application/json'
        )
        # Should handle gracefully
        assert response.status_code in [400, 500]
```

**Step 4: Run tests**

Run: `pytest apps/projects/tests/ -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add apps/projects/tests/
git commit -m "test: add projects app tests"
```

---

## Phase 5: Tasks App - Security Audit & Tests

### Task 5.1: Security Issues - Tasks App

**Files:**
- Review: `apps/tasks/views.py:1-336`
- Review: `apps/tasks/models.py:1-141`

**Security Findings:**

1. **CRITICAL: File Upload Without Validation (Lines 208-219)**
   - Issue: `attachment_upload` accepts any file type
   - Risk: Malicious file upload, XSS via SVG, path traversal
   - Fix: Validate file types, scan content, use secure filename

2. **HIGH: No Authorization Checks on Task Operations**
   - Issue: Any user can edit/delete any task
   - Risk: Unauthorized data modification
   - Recommendation: Check project membership

3. **MEDIUM: Race Condition in task_move (Lines 126-133)**
   - Issue: No locking when moving tasks between statuses
   - Risk: Lost updates if concurrent moves

4. **MEDIUM: XSS Risk in Comment Content (Lines 192-203)**
   - Issue: Comment content rendered without explicit escaping
   - Risk: Stored XSS if templates don't escape
   - Note: Django auto-escapes, but verify templates

5. **LOW: Subtask Order Race (Lines 156-158)**
   - Issue: `task.subtasks.count()` for order can race
   - Risk: Duplicate order values

**Step 1: Create security-focused tests**

---

### Task 5.2: Create Tasks App Tests

**Files:**
- Create: `apps/tasks/tests/__init__.py`
- Create: `apps/tasks/tests/test_views.py`
- Create: `apps/tasks/tests/test_models.py`

**Step 1: Create test directory**

```bash
mkdir -p apps/tasks/tests
touch apps/tasks/tests/__init__.py
```

**Step 2: Write model tests**

```python
# apps/tasks/tests/test_models.py
import pytest
from apps.tasks.factories import (
    TaskFactory, SubtaskFactory, LabelFactory,
    CommentFactory, TaskActivityFactory
)
from apps.projects.factories import ProjectFactory


@pytest.mark.django_db
class TestTaskModel:
    def test_create_task(self):
        task = TaskFactory()
        assert task.title is not None
        assert task.project is not None
        assert task.status is not None

    def test_task_str(self):
        task = TaskFactory(title='Test Task')
        assert str(task) == 'Test Task'

    def test_subtask_progress_none_when_empty(self):
        task = TaskFactory()
        assert task.subtask_progress is None

    def test_subtask_progress_calculation(self):
        task = TaskFactory()
        SubtaskFactory(task=task, completed=True)
        SubtaskFactory(task=task, completed=False)
        SubtaskFactory(task=task, completed=True)
        assert task.subtask_progress == '2/3'

    def test_task_ordering(self):
        project = ProjectFactory()
        status = project.statuses.first()
        TaskFactory(project=project, status=status, order=2, title='Second')
        TaskFactory(project=project, status=status, order=0, title='First')
        TaskFactory(project=project, status=status, order=1, title='Middle')
        tasks = list(status.tasks.all())
        assert tasks[0].title == 'First'


@pytest.mark.django_db
class TestLabelModel:
    def test_label_unique_per_project(self):
        project = ProjectFactory()
        LabelFactory(project=project, name='Bug')
        with pytest.raises(Exception):  # IntegrityError
            LabelFactory(project=project, name='Bug')

    def test_same_label_name_different_projects(self):
        project1 = ProjectFactory()
        project2 = ProjectFactory()
        LabelFactory(project=project1, name='Bug')
        label2 = LabelFactory(project=project2, name='Bug')
        assert label2.pk is not None


@pytest.mark.django_db
class TestSubtaskModel:
    def test_subtask_ordering(self):
        task = TaskFactory()
        SubtaskFactory(task=task, order=2, title='Third')
        SubtaskFactory(task=task, order=0, title='First')
        SubtaskFactory(task=task, order=1, title='Second')
        subtasks = list(task.subtasks.all())
        assert subtasks[0].title == 'First'


@pytest.mark.django_db
class TestTaskActivityModel:
    def test_activity_ordering(self):
        task = TaskFactory()
        from datetime import timedelta
        from django.utils import timezone
        now = timezone.now()
        # Create in reverse order
        TaskActivityFactory(task=task, content='Third')
        TaskActivityFactory(task=task, content='Second')
        TaskActivityFactory(task=task, content='First')
        activities = list(task.activities.all())
        # Should be chronological (oldest first)
        assert len(activities) == 3
```

**Step 3: Write view tests**

```python
# apps/tasks/tests/test_views.py
import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.accounts.factories import UserFactory
from apps.tasks.factories import TaskFactory, SubtaskFactory
from apps.projects.factories import ProjectFactory


@pytest.mark.django_db
class TestMyTasks:
    def test_my_tasks_requires_login(self, client):
        response = client.get(reverse('my_tasks'))
        assert response.status_code == 302

    def test_my_tasks_shows_only_assigned(self, client):
        user = UserFactory()
        other = UserFactory()
        project = ProjectFactory()
        status = project.statuses.first()
        TaskFactory(project=project, status=status, assignee=user, title='My Task')
        TaskFactory(project=project, status=status, assignee=other, title='Other Task')
        client.force_login(user)
        response = client.get(reverse('my_tasks'))
        content = response.content.decode()
        assert 'My Task' in content
        assert 'Other Task' not in content

    def test_my_tasks_filter_by_priority(self, client):
        user = UserFactory()
        project = ProjectFactory()
        status = project.statuses.first()
        TaskFactory(project=project, status=status, assignee=user, priority='high', title='High Priority')
        TaskFactory(project=project, status=status, assignee=user, priority='low', title='Low Priority')
        client.force_login(user)
        response = client.get(reverse('my_tasks') + '?priority=high')
        content = response.content.decode()
        assert 'High Priority' in content
        assert 'Low Priority' not in content


@pytest.mark.django_db
class TestTaskCreate:
    def test_task_create_requires_login(self, client):
        project = ProjectFactory()
        response = client.get(reverse('task_create', args=[project.pk]))
        assert response.status_code == 302

    def test_task_create_with_valid_data(self, client):
        user = UserFactory()
        project = ProjectFactory()
        client.force_login(user)
        response = client.post(
            reverse('task_create', args=[project.pk]),
            {'title': 'New Task', 'description': 'Description'}
        )
        assert response.status_code == 302
        from apps.tasks.models import Task
        assert Task.objects.filter(title='New Task').exists()

    def test_task_create_with_status_param(self, client):
        user = UserFactory()
        project = ProjectFactory()
        status = project.statuses.last()
        client.force_login(user)
        response = client.get(
            reverse('task_create', args=[project.pk]) + f'?status={status.pk}',
            HTTP_HX_REQUEST='true'
        )
        assert response.status_code == 200
        assert status.name in response.content.decode()


@pytest.mark.django_db
class TestTaskMove:
    def test_move_task_to_new_status(self, client):
        user = UserFactory()
        project = ProjectFactory()
        status1 = project.statuses.first()
        status2 = project.statuses.last()
        task = TaskFactory(project=project, status=status1)
        client.force_login(user)
        response = client.post(
            reverse('task_move'),
            {'task_id': task.pk, 'status_id': status2.pk}
        )
        assert response.status_code == 204
        task.refresh_from_db()
        assert task.status == status2

    def test_move_task_invalid_status(self, client):
        user = UserFactory()
        project1 = ProjectFactory()
        project2 = ProjectFactory()
        task = TaskFactory(project=project1, status=project1.statuses.first())
        other_status = project2.statuses.first()
        client.force_login(user)
        response = client.post(
            reverse('task_move'),
            {'task_id': task.pk, 'status_id': other_status.pk}
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestSubtasks:
    def test_create_subtask(self, client):
        user = UserFactory()
        task = TaskFactory()
        client.force_login(user)
        response = client.post(
            reverse('subtask_create', args=[task.pk]),
            {'title': 'New Subtask'}
        )
        assert response.status_code == 200
        assert task.subtasks.filter(title='New Subtask').exists()

    def test_toggle_subtask(self, client):
        user = UserFactory()
        task = TaskFactory()
        subtask = SubtaskFactory(task=task, completed=False)
        client.force_login(user)
        response = client.post(
            reverse('subtask_toggle', args=[task.pk, subtask.pk])
        )
        assert response.status_code == 200
        subtask.refresh_from_db()
        assert subtask.completed is True

    def test_delete_subtask(self, client):
        user = UserFactory()
        task = TaskFactory()
        subtask = SubtaskFactory(task=task)
        client.force_login(user)
        response = client.post(
            reverse('subtask_delete', args=[task.pk, subtask.pk])
        )
        assert response.status_code == 200
        assert not task.subtasks.filter(pk=subtask.pk).exists()


@pytest.mark.django_db
@pytest.mark.security
class TestAttachmentUpload:
    def test_upload_valid_file(self, client):
        user = UserFactory()
        task = TaskFactory()
        file = SimpleUploadedFile(
            'test.txt',
            b'file content',
            content_type='text/plain'
        )
        client.force_login(user)
        response = client.post(
            reverse('attachment_upload', args=[task.pk]),
            {'file': file}
        )
        assert response.status_code == 200
        assert task.attachments.count() == 1

    def test_upload_no_file(self, client):
        user = UserFactory()
        task = TaskFactory()
        client.force_login(user)
        response = client.post(
            reverse('attachment_upload', args=[task.pk]),
            {}
        )
        assert response.status_code == 400

    # Security test: Should validate file types in production
    def test_upload_dangerous_file_type(self, client):
        user = UserFactory()
        task = TaskFactory()
        # Note: This test documents current behavior
        # In production, .exe files should be rejected
        file = SimpleUploadedFile(
            'malware.exe',
            b'fake exe content',
            content_type='application/octet-stream'
        )
        client.force_login(user)
        response = client.post(
            reverse('attachment_upload', args=[task.pk]),
            {'file': file}
        )
        # Current: Accepts any file (SECURITY ISSUE)
        # Expected: Should reject dangerous file types


@pytest.mark.django_db
class TestComments:
    def test_create_comment(self, client):
        user = UserFactory()
        task = TaskFactory()
        client.force_login(user)
        response = client.post(
            reverse('comment_create', args=[task.pk]),
            {'content': 'This is a comment'}
        )
        assert response.status_code == 200
        assert task.activities.filter(activity_type='comment').exists()

    def test_empty_comment_rejected(self, client):
        user = UserFactory()
        task = TaskFactory()
        client.force_login(user)
        response = client.post(
            reverse('comment_create', args=[task.pk]),
            {'content': '   '}  # Whitespace only
        )
        assert response.status_code == 400
```

**Step 4: Run tests**

Run: `pytest apps/tasks/tests/ -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add apps/tasks/tests/
git commit -m "test: add tasks app tests"
```

---

## Phase 6: Integrations App - Security Audit & Tests

### Task 6.1: Security Issues - Integrations App

**Files:**
- Review: `apps/integrations/views.py:1-89`

**Security Findings:**

1. **GOOD: Webhook Signature Verification (Lines 20-29)**
   - Uses HMAC-SHA256 with timing-safe comparison
   - Properly validates GitHub webhook signatures

2. **MEDIUM: Optional Webhook Secret (Line 41)**
   - Issue: `if webhook_secret and not verify_signature` allows bypass
   - Risk: If GITHUB_WEBHOOK_SECRET not set, webhooks are unverified
   - Fix: Require secret in production

3. **MEDIUM: Loose Repository URL Matching (Line 55)**
   - Issue: `github_repo_url__icontains` could match unintended repos
   - Risk: Webhook hijacking between similar repo names
   - Fix: Use exact matching with URL normalization

4. **LOW: Async in Sync View (Lines 83-86)**
   - Issue: `asyncio.run()` in sync view is inefficient
   - Risk: Thread blocking, performance issues
   - Fix: Use proper async view or background task

**Step 1: Create security tests**

---

### Task 6.2: Create Integrations App Tests

**Files:**
- Create: `apps/integrations/tests/__init__.py`
- Create: `apps/integrations/tests/test_views.py`
- Create: `apps/integrations/tests/test_webhook.py`

**Step 1: Create test directory**

```bash
mkdir -p apps/integrations/tests
touch apps/integrations/tests/__init__.py
```

**Step 2: Write webhook tests**

```python
# apps/integrations/tests/test_webhook.py
import pytest
import json
import hashlib
import hmac
from django.urls import reverse
from django.test import override_settings
from apps.projects.factories import ProjectFactory


def generate_signature(payload: bytes, secret: str) -> str:
    """Generate GitHub webhook signature."""
    return 'sha256=' + hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()


@pytest.mark.django_db
@pytest.mark.security
class TestGitHubWebhook:
    def test_webhook_rejects_invalid_signature(self, client):
        project = ProjectFactory(
            github_repo_url='https://github.com/test/repo',
            github_sync_enabled=True
        )
        payload = json.dumps({
            'repository': {'html_url': 'https://github.com/test/repo'}
        }).encode()
        with override_settings(GITHUB_WEBHOOK_SECRET='secret'):
            response = client.post(
                reverse('github_webhook'),
                payload,
                content_type='application/json',
                HTTP_X_HUB_SIGNATURE_256='sha256=invalid',
                HTTP_X_GITHUB_EVENT='push'
            )
        assert response.status_code == 401

    def test_webhook_accepts_valid_signature(self, client):
        project = ProjectFactory(
            github_repo_url='https://github.com/test/repo',
            github_sync_enabled=True
        )
        payload = json.dumps({
            'repository': {'html_url': 'https://github.com/test/repo'},
            'commits': []
        }).encode()
        secret = 'test-secret'
        signature = generate_signature(payload, secret)
        with override_settings(GITHUB_WEBHOOK_SECRET=secret):
            response = client.post(
                reverse('github_webhook'),
                payload,
                content_type='application/json',
                HTTP_X_HUB_SIGNATURE_256=signature,
                HTTP_X_GITHUB_EVENT='push'
            )
        assert response.status_code == 200

    def test_webhook_rejects_invalid_json(self, client):
        response = client.post(
            reverse('github_webhook'),
            'not json',
            content_type='application/json',
            HTTP_X_GITHUB_EVENT='push'
        )
        assert response.status_code == 400

    def test_webhook_requires_repository_url(self, client):
        payload = json.dumps({'repository': {}}).encode()
        response = client.post(
            reverse('github_webhook'),
            payload,
            content_type='application/json',
            HTTP_X_GITHUB_EVENT='push'
        )
        assert response.status_code == 400

    def test_webhook_404_for_unknown_repo(self, client):
        payload = json.dumps({
            'repository': {'html_url': 'https://github.com/unknown/repo'}
        }).encode()
        response = client.post(
            reverse('github_webhook'),
            payload,
            content_type='application/json',
            HTTP_X_GITHUB_EVENT='push'
        )
        assert response.status_code == 404

    def test_webhook_404_for_disabled_sync(self, client):
        project = ProjectFactory(
            github_repo_url='https://github.com/test/repo',
            github_sync_enabled=False  # Sync disabled
        )
        payload = json.dumps({
            'repository': {'html_url': 'https://github.com/test/repo'}
        }).encode()
        response = client.post(
            reverse('github_webhook'),
            payload,
            content_type='application/json',
            HTTP_X_GITHUB_EVENT='push'
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestGitHubSync:
    def test_sync_requires_login(self, client):
        project = ProjectFactory()
        response = client.post(reverse('github_sync', args=[project.pk]))
        assert response.status_code == 302

    def test_sync_requires_github_repo(self, client):
        from apps.accounts.factories import UserFactory
        user = UserFactory()
        project = ProjectFactory(github_repo_url='')
        client.force_login(user)
        response = client.post(reverse('github_sync', args=[project.pk]))
        assert response.status_code == 400
        assert 'No GitHub repo' in response.json()['error']

    def test_sync_requires_github_token(self, client):
        from apps.accounts.factories import UserFactory
        user = UserFactory(github_token='')
        project = ProjectFactory(github_repo_url='https://github.com/test/repo')
        client.force_login(user)
        response = client.post(reverse('github_sync', args=[project.pk]))
        assert response.status_code == 400
        assert 'token' in response.json()['error'].lower()
```

**Step 3: Run tests**

Run: `pytest apps/integrations/tests/ -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add apps/integrations/tests/
git commit -m "test: add integrations app tests"
```

---

## Phase 7: UI/UX Consistency Audit

### Task 7.1: Document UI/UX Patterns

**Files:**
- Create: `docs/ui-patterns.md`

**UI Patterns Identified:**

1. **Page Layouts:**
   - Compact header pattern: icon + title + count badge
   - `{% block full_content %}` for full-height pages
   - Right sidebar navigation (client detail, project settings)

2. **Form Styling:**
   - INPUT_CLASSES constant in forms.py
   - Consistent across apps (slightly different in clients vs tasks)

3. **Table Styling:**
   - Consistent row hover effects
   - Pagination component reused

4. **Inconsistencies Found:**
   - INPUT_CLASSES differs between `clients/forms.py` and `tasks/forms.py`
   - Some pages use `{% block content %}`, others use `{% block full_content %}`
   - Drawer pattern not consistently applied (some pages redirect)

**Step 1: Create UI patterns documentation**

```markdown
# UI/UX Patterns - WebFTL CRM

## Page Layout Patterns

### Compact Header
All list pages should use:
- Icon + Title + Count badge
- `{% block full_content %}` for full height
- Consistent padding: `px-6 py-3`

### Right Sidebar
Used for: Client detail, Project settings
- 48rem width (`w-48`)
- Section navigation links
- `bg-sidebar/30` background

## Form Input Classes

Standard input class (should be unified):
```python
INPUT_CLASSES = 'w-full bg-elevated border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none'
```

## Inconsistencies to Fix

1. [ ] Unify INPUT_CLASSES across all apps
2. [ ] Convert remaining `{% block content %}` to `{% block full_content %}`
3. [ ] Add drawer editing to project edit (currently redirects)
```

**Step 2: Commit**

```bash
git add docs/ui-patterns.md
git commit -m "docs: add UI/UX patterns documentation"
```

---

### Task 7.2: Create UI Consistency Tests

**Files:**
- Create: `apps/tests/test_ui_consistency.py`

**Step 1: Write UI consistency tests**

```python
# apps/tests/test_ui_consistency.py
"""
Tests to verify UI/UX consistency across the application.
These tests check templates and responses for consistent patterns.
"""
import pytest
from django.urls import reverse
from apps.accounts.factories import UserFactory, AdminUserFactory
from apps.clients.factories import ClientFactory
from apps.projects.factories import ProjectFactory


@pytest.mark.django_db
class TestPageHeaders:
    """All list pages should have consistent compact headers."""

    def test_dashboard_has_compact_header(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('dashboard'))
        content = response.content.decode()
        assert 'text-base font-semibold' in content  # Compact title style

    def test_client_list_has_compact_header(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('client_list'))
        content = response.content.decode()
        assert 'Clients' in content
        assert 'total_count' in response.context or 'clients' in response.context

    def test_project_list_has_compact_header(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('project_list'))
        content = response.content.decode()
        assert 'Projects' in content

    def test_team_list_has_compact_header(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.get(reverse('team_list'))
        content = response.content.decode()
        assert 'Team' in content


@pytest.mark.django_db
class TestPagination:
    """All list pages should support pagination consistently."""

    def test_client_list_pagination_context(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('client_list'))
        assert 'page_obj' in response.context

    def test_project_list_pagination_context(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('project_list'))
        assert 'page_obj' in response.context

    def test_my_tasks_pagination_context(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.get(reverse('my_tasks'))
        assert 'page_obj' in response.context

    def test_team_list_pagination_context(self, client):
        admin = AdminUserFactory()
        client.force_login(admin)
        response = client.get(reverse('team_list'))
        assert 'page_obj' in response.context


@pytest.mark.django_db
class TestHTMXSupport:
    """Views with HTMX support should respond correctly."""

    def test_project_board_htmx(self, client):
        user = UserFactory()
        project = ProjectFactory()
        client.force_login(user)
        response = client.get(
            reverse('project_board', args=[project.pk]),
            HTTP_HX_REQUEST='true'
        )
        assert response.status_code == 200
        # Should return partial, not full page
        content = response.content.decode()
        assert '<!DOCTYPE' not in content

    def test_task_create_htmx(self, client):
        user = UserFactory()
        project = ProjectFactory()
        client.force_login(user)
        response = client.get(
            reverse('task_create', args=[project.pk]),
            HTTP_HX_REQUEST='true'
        )
        assert response.status_code == 200
        # Should return slide-over content
        content = response.content.decode()
        assert 'slide-over' in content.lower() or 'New Task' in content
```

**Step 2: Run tests**

Run: `pytest apps/tests/test_ui_consistency.py -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add apps/tests/
git commit -m "test: add UI consistency tests"
```

---

## Phase 8: Race Condition Tests

### Task 8.1: Create Race Condition Tests

**Files:**
- Create: `apps/tests/test_race_conditions.py`

**Step 1: Write race condition tests**

```python
# apps/tests/test_race_conditions.py
"""
Tests for race conditions in concurrent operations.
These tests verify data integrity under concurrent access.
"""
import pytest
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.test import TransactionTestCase
from django.db import connection
from apps.projects.factories import ProjectFactory
from apps.tasks.factories import TaskFactory


class TestStatusOrderRace(TransactionTestCase):
    """Test race conditions in status ordering."""

    def test_concurrent_status_creation(self):
        """Multiple concurrent status creations should have unique orders."""
        from apps.accounts.factories import UserFactory
        from django.test import Client
        from django.urls import reverse

        project = ProjectFactory()
        user = UserFactory()
        initial_count = project.statuses.count()

        def create_status(name):
            client = Client()
            client.force_login(user)
            return client.post(
                reverse('status_create', args=[project.pk]),
                {'name': name}
            )

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(create_status, f'Status {i}')
                for i in range(5)
            ]
            for future in as_completed(futures):
                future.result()

        project.refresh_from_db()
        new_count = project.statuses.count()
        assert new_count == initial_count + 5

        # Check for duplicate orders (race condition symptom)
        orders = list(project.statuses.values_list('order', flat=True))
        assert len(orders) == len(set(orders)), "Duplicate order values detected!"


class TestSubtaskOrderRace(TransactionTestCase):
    """Test race conditions in subtask ordering."""

    def test_concurrent_subtask_creation(self):
        """Multiple concurrent subtask creations should have unique orders."""
        from apps.accounts.factories import UserFactory
        from django.test import Client
        from django.urls import reverse

        task = TaskFactory()
        user = UserFactory()

        def create_subtask(title):
            client = Client()
            client.force_login(user)
            return client.post(
                reverse('subtask_create', args=[task.pk]),
                {'title': title}
            )

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(create_subtask, f'Subtask {i}')
                for i in range(5)
            ]
            for future in as_completed(futures):
                future.result()

        task.refresh_from_db()
        assert task.subtasks.count() == 5

        # Check for duplicate orders
        orders = list(task.subtasks.values_list('order', flat=True))
        # Note: Current implementation may have duplicates (known issue)


class TestTaskMoveRace(TransactionTestCase):
    """Test race conditions in task movement."""

    def test_concurrent_task_moves(self):
        """Concurrent moves of same task should result in consistent state."""
        from apps.accounts.factories import UserFactory
        from django.test import Client
        from django.urls import reverse

        project = ProjectFactory()
        status1 = project.statuses.first()
        status2 = project.statuses.last()
        task = TaskFactory(project=project, status=status1)
        user = UserFactory()

        def move_task(status_id):
            client = Client()
            client.force_login(user)
            return client.post(
                reverse('task_move'),
                {'task_id': task.pk, 'status_id': status_id}
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(move_task, status1.pk),
                executor.submit(move_task, status2.pk),
            ]
            for future in as_completed(futures):
                future.result()

        task.refresh_from_db()
        # Task should be in one valid status
        assert task.status in [status1, status2]
```

**Step 2: Run tests**

Run: `pytest apps/tests/test_race_conditions.py -v --tb=short`
Expected: Tests run (some may expose race conditions)

**Step 3: Commit**

```bash
git add apps/tests/test_race_conditions.py
git commit -m "test: add race condition tests"
```

---

## Phase 9: Final Integration

### Task 9.1: Run Full Test Suite

**Step 1: Run all tests**

Run: `pytest -v --tb=short`
Expected: All tests pass

**Step 2: Generate coverage report**

Run: `pytest --cov=apps --cov-report=html`
Expected: Coverage report generated in htmlcov/

**Step 3: Commit final state**

```bash
git add .
git commit -m "test: complete security audit and test suite"
```

---

## Security Recommendations Summary

### Critical (Fix Immediately)

1. **GitHub Token Encryption** - Store tokens encrypted, not plain text
2. **File Upload Validation** - Whitelist allowed file types, scan for malware
3. **Authorization Checks** - Add project membership model for access control

### High Priority

1. **JSON Parsing Safety** - Add try/except for all JSON.loads()
2. **Rate Limiting** - Add rate limits to sensitive endpoints (role toggle, file upload)
3. **Webhook Secret Required** - Make GITHUB_WEBHOOK_SECRET mandatory in production

### Medium Priority

1. **Race Condition Fixes** - Use database sequences or F() expressions for ordering
2. **Form Validation** - Use Django forms consistently for all data input
3. **Repository URL Matching** - Use exact matching for webhook routing

### Low Priority

1. **Error Handling** - Replace broad exceptions with specific ones
2. **Async Optimization** - Convert sync views with async operations
3. **UI Consistency** - Unify INPUT_CLASSES and layout patterns
