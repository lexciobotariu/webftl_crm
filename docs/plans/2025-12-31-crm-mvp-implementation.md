# WebFTL CRM MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a CRM for small agencies with client management, Kanban project tracking, and GitHub integration.

**Architecture:** Django monolith with HTMX for interactivity. Five apps: accounts, clients, projects, tasks, integrations. PostgreSQL database in Docker. Single-tenant (one organization per deployment).

**Tech Stack:** Python 3.12 (local venv), Django 5.1, django-allauth, HTMX 2.0, Alpine.js 3.x, Tailwind CSS (CDN), PostgreSQL 16 (Docker)

---

## Phase 1: Project Foundation

### Task 1.0: Python Virtual Environment Setup

**Files:**
- Create: `.venv/` (virtual environment directory)
- Create: `.gitignore`

**Step 1: Create virtual environment with Python 3.12**

```bash
python3.12 -m venv .venv
```

**Step 2: Create .gitignore**

```
# Virtual environment
.venv/
venv/

# Python
__pycache__/
*.py[cod]
*$py.class
*.so

# Environment
.env

# Django
*.log
local_settings.py
db.sqlite3
media/

# Static files
staticfiles/

# IDE
.idea/
.vscode/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
```

**Step 3: Activate venv and verify Python version**

```bash
source .venv/bin/activate
python --version  # Should show Python 3.12.x
```

**Step 4: Commit**

```bash
git add .gitignore
git commit -m "feat: add .gitignore for Python/Django project"
```

> **Note:** For all subsequent commands in this plan, always activate the virtual environment first:
> ```bash
> source .venv/bin/activate
> ```

---

### Task 1.1: PostgreSQL Docker Setup

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`

**Step 1: Create docker-compose.yml (PostgreSQL only)**

```yaml
services:
  db:
    image: postgres:16
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-webftl_crm}
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
    ports:
      - "5432:5432"

volumes:
  postgres_data:
```

**Step 2: Create .env.example**

```
DEBUG=True
SECRET_KEY=your-secret-key-here
POSTGRES_DB=webftl_crm
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
DATABASE_URL=postgres://postgres:postgres@localhost:5432/webftl_crm
```

> **Note:** DATABASE_URL uses `localhost` since Django runs locally, not in Docker.

**Step 3: Start PostgreSQL**

```bash
docker-compose up -d
```

**Step 4: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "feat: add Docker Compose for PostgreSQL"
```

---

### Task 1.2: Django Project Setup

**Files:**
- Create: `requirements.txt`
- Create: `config/__init__.py`
- Create: `config/settings.py`
- Create: `config/urls.py`
- Create: `config/wsgi.py`
- Create: `manage.py`

**Step 1: Create requirements.txt**

```
Django==5.1.4
django-allauth==65.3.0
django-htmx==1.27.0
psycopg[binary]==3.3.2
dj-database-url==3.0.1
python-dotenv==1.2.1
whitenoise==6.11.0
Pillow==12.0.0
httpx==0.28.1
```

**Step 2: Create manage.py**

```python
#!/usr/bin/env python
import os
import sys

def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed?"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
```

**Step 3: Create config/__init__.py**

```python
# Empty file
```

**Step 4: Create config/settings.py**

```python
import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
DEBUG = os.getenv('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    # Third party
    'allauth',
    'allauth.account',
    'django_htmx',
    # Local apps
    'apps.accounts',
    'apps.clients',
    'apps.projects',
    'apps.tasks',
    'apps.integrations',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': dj_database_url.config(
        default='postgres://postgres:postgres@db:5432/webftl_crm',
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Auth
AUTH_USER_MODEL = 'accounts.User'
SITE_ID = 1
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

# Allauth
ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_EMAIL_VERIFICATION = 'none'  # Change to 'mandatory' in production
```

**Step 5: Create config/urls.py**

```python
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', include('apps.accounts.urls')),
    path('clients/', include('apps.clients.urls')),
    path('projects/', include('apps.projects.urls')),
    path('tasks/', include('apps.tasks.urls')),
    path('integrations/', include('apps.integrations.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

**Step 6: Create config/wsgi.py**

```python
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
application = get_wsgi_application()
```

**Step 7: Create app directories**

```bash
mkdir -p apps/accounts apps/clients apps/projects apps/tasks apps/integrations
mkdir -p templates/components templates/accounts templates/clients templates/projects templates/tasks
mkdir -p static/css
touch apps/__init__.py
touch apps/accounts/__init__.py apps/clients/__init__.py apps/projects/__init__.py apps/tasks/__init__.py apps/integrations/__init__.py
```

**Step 8: Commit**

```bash
git add .
git commit -m "feat: add Django project structure"
```

---

### Task 1.3: Base Template with Tailwind and HTMX

**Files:**
- Create: `templates/base.html`
- Create: `templates/components/sidebar.html`
- Create: `static/css/custom.css`

**Step 1: Create templates/base.html**

```html
<!DOCTYPE html>
<html lang="en" class="h-full bg-gray-50">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}WebFTL CRM{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@2.0.4"></script>
    <script defer src="https://unpkg.com/alpinejs@3.14.8/dist/cdn.min.js"></script>
    <link rel="stylesheet" href="{% load static %}{% static 'css/custom.css' %}">
</head>
<body class="h-full" hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>
    {% if user.is_authenticated %}
    <div class="min-h-full flex">
        {% include "components/sidebar.html" %}
        <main class="flex-1 p-8">
            {% block content %}{% endblock %}
        </main>
    </div>
    {% else %}
    <main class="min-h-full flex items-center justify-center">
        {% block auth_content %}{% endblock %}
    </main>
    {% endif %}

    <div id="slide-over" class="hidden"></div>
    <div id="modal" class="hidden"></div>
</body>
</html>
```

**Step 2: Create templates/components/sidebar.html**

```html
<aside class="w-64 bg-gray-900 text-white min-h-screen p-4">
    <div class="mb-8">
        <h1 class="text-xl font-bold">WebFTL CRM</h1>
    </div>
    <nav class="space-y-2">
        <a href="{% url 'dashboard' %}"
           class="block px-4 py-2 rounded hover:bg-gray-800 {% if request.resolver_match.url_name == 'dashboard' %}bg-gray-800{% endif %}">
            Dashboard
        </a>
        <a href="{% url 'client_list' %}"
           class="block px-4 py-2 rounded hover:bg-gray-800 {% if 'client' in request.resolver_match.url_name %}bg-gray-800{% endif %}">
            Clients
        </a>
        <a href="{% url 'project_list' %}"
           class="block px-4 py-2 rounded hover:bg-gray-800 {% if 'project' in request.resolver_match.url_name %}bg-gray-800{% endif %}">
            Projects
        </a>
        <a href="{% url 'my_tasks' %}"
           class="block px-4 py-2 rounded hover:bg-gray-800 {% if request.resolver_match.url_name == 'my_tasks' %}bg-gray-800{% endif %}">
            My Tasks
        </a>
        {% if user.role == 'admin' %}
        <a href="{% url 'team_list' %}"
           class="block px-4 py-2 rounded hover:bg-gray-800 {% if 'team' in request.resolver_match.url_name %}bg-gray-800{% endif %}">
            Team
        </a>
        {% endif %}
    </nav>
    <div class="absolute bottom-4 left-4 right-4">
        <div class="px-4 py-2 text-sm text-gray-400">{{ user.email }}</div>
        <a href="{% url 'account_logout' %}" class="block px-4 py-2 rounded hover:bg-gray-800 text-red-400">
            Logout
        </a>
    </div>
</aside>
```

**Step 3: Create static/css/custom.css**

```css
/* Custom scrollbar */
::-webkit-scrollbar {
    width: 8px;
}

::-webkit-scrollbar-track {
    background: #f1f1f1;
}

::-webkit-scrollbar-thumb {
    background: #888;
    border-radius: 4px;
}

/* HTMX loading indicator */
.htmx-request .htmx-indicator {
    display: inline-block;
}

.htmx-indicator {
    display: none;
}

/* Slide-over panel */
.slide-over-panel {
    position: fixed;
    top: 0;
    right: 0;
    width: 40rem;
    max-width: 100%;
    height: 100vh;
    background: white;
    box-shadow: -4px 0 20px rgba(0, 0, 0, 0.1);
    z-index: 50;
    overflow-y: auto;
}

/* Kanban drag styles */
.dragging {
    opacity: 0.5;
}

.drag-over {
    border: 2px dashed #3b82f6;
}
```

**Step 4: Commit**

```bash
git add templates/ static/
git commit -m "feat: add base template with Tailwind, HTMX, Alpine"
```

---

## Phase 2: Accounts App

### Task 2.1: Custom User Model

**Files:**
- Create: `apps/accounts/models.py`
- Create: `apps/accounts/admin.py`
- Create: `apps/accounts/managers.py`

**Step 1: Create apps/accounts/managers.py**

```python
from django.contrib.auth.models import BaseUserManager


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        return self.create_user(email, password, **extra_fields)
```

**Step 2: Create apps/accounts/models.py**

```python
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('member', 'Member'),
    ]

    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    github_token = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']

    def __str__(self):
        return self.email

    @property
    def is_admin(self):
        return self.role == 'admin'
```

**Step 3: Create apps/accounts/admin.py**

```python
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'name', 'role', 'is_active', 'created_at')
    list_filter = ('role', 'is_active', 'is_staff')
    search_fields = ('email', 'name')
    ordering = ('email',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('name', 'role', 'github_token')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'name', 'password1', 'password2', 'role'),
        }),
    )
```

**Step 4: Commit**

```bash
git add apps/accounts/
git commit -m "feat: add custom User model with roles"
```

---

### Task 2.2: Account URLs and Views

**Files:**
- Create: `apps/accounts/urls.py`
- Create: `apps/accounts/views.py`
- Create: `templates/accounts/dashboard.html`
- Create: `templates/accounts/team_list.html`

**Step 1: Create apps/accounts/urls.py**

```python
from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('team/', views.team_list, name='team_list'),
    path('team/<int:pk>/toggle-role/', views.toggle_role, name='toggle_role'),
]
```

**Step 2: Create apps/accounts/views.py**

```python
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404

from .models import User
from apps.clients.models import Client
from apps.projects.models import Project
from apps.tasks.models import Task


@login_required
def dashboard(request):
    context = {
        'client_count': Client.objects.count(),
        'project_count': Project.objects.count(),
        'my_task_count': Task.objects.filter(assignee=request.user).exclude(status__name='Done').count(),
        'recent_tasks': Task.objects.filter(assignee=request.user).order_by('-updated_at')[:5],
    }
    return render(request, 'accounts/dashboard.html', context)


@login_required
def team_list(request):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    users = User.objects.all().order_by('name')
    return render(request, 'accounts/team_list.html', {'users': users})


@login_required
def toggle_role(request, pk):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    user = get_object_or_404(User, pk=pk)
    if user != request.user:  # Can't change own role
        user.role = 'member' if user.role == 'admin' else 'admin'
        user.save()
    return render(request, 'accounts/partials/user_row.html', {'user': user})
```

**Step 3: Create templates/accounts/dashboard.html**

```html
{% extends "base.html" %}

{% block title %}Dashboard - WebFTL CRM{% endblock %}

{% block content %}
<h1 class="text-2xl font-bold mb-8">Dashboard</h1>

<div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
    <div class="bg-white rounded-lg shadow p-6">
        <div class="text-3xl font-bold text-blue-600">{{ client_count }}</div>
        <div class="text-gray-500">Clients</div>
    </div>
    <div class="bg-white rounded-lg shadow p-6">
        <div class="text-3xl font-bold text-green-600">{{ project_count }}</div>
        <div class="text-gray-500">Projects</div>
    </div>
    <div class="bg-white rounded-lg shadow p-6">
        <div class="text-3xl font-bold text-orange-600">{{ my_task_count }}</div>
        <div class="text-gray-500">My Active Tasks</div>
    </div>
</div>

<div class="bg-white rounded-lg shadow">
    <div class="p-4 border-b">
        <h2 class="text-lg font-semibold">My Recent Tasks</h2>
    </div>
    <div class="divide-y">
        {% for task in recent_tasks %}
        <a href="{% url 'project_board' task.project.pk %}?task={{ task.pk }}"
           class="block p-4 hover:bg-gray-50">
            <div class="font-medium">{{ task.title }}</div>
            <div class="text-sm text-gray-500">{{ task.project.name }} &middot; {{ task.status.name }}</div>
        </a>
        {% empty %}
        <div class="p-4 text-gray-500">No tasks assigned yet.</div>
        {% endfor %}
    </div>
</div>
{% endblock %}
```

**Step 4: Create templates/accounts/team_list.html**

```html
{% extends "base.html" %}

{% block title %}Team - WebFTL CRM{% endblock %}

{% block content %}
<div class="flex justify-between items-center mb-8">
    <h1 class="text-2xl font-bold">Team</h1>
    <a href="{% url 'account_signup' %}" class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
        Invite Member
    </a>
</div>

<div class="bg-white rounded-lg shadow">
    <table class="w-full">
        <thead class="bg-gray-50">
            <tr>
                <th class="px-6 py-3 text-left text-sm font-semibold text-gray-900">Name</th>
                <th class="px-6 py-3 text-left text-sm font-semibold text-gray-900">Email</th>
                <th class="px-6 py-3 text-left text-sm font-semibold text-gray-900">Role</th>
                <th class="px-6 py-3 text-left text-sm font-semibold text-gray-900">Actions</th>
            </tr>
        </thead>
        <tbody class="divide-y">
            {% for member in users %}
            {% include "accounts/partials/user_row.html" with user=member %}
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
```

**Step 5: Create templates/accounts/partials/user_row.html**

```html
<tr id="user-{{ user.pk }}">
    <td class="px-6 py-4">{{ user.name }}</td>
    <td class="px-6 py-4">{{ user.email }}</td>
    <td class="px-6 py-4">
        <span class="px-2 py-1 text-xs rounded {% if user.role == 'admin' %}bg-purple-100 text-purple-800{% else %}bg-gray-100 text-gray-800{% endif %}">
            {{ user.get_role_display }}
        </span>
    </td>
    <td class="px-6 py-4">
        {% if user != request.user %}
        <button hx-post="{% url 'toggle_role' user.pk %}"
                hx-target="#user-{{ user.pk }}"
                hx-swap="outerHTML"
                class="text-blue-600 hover:underline">
            Make {% if user.role == 'admin' %}Member{% else %}Admin{% endif %}
        </button>
        {% endif %}
    </td>
</tr>
```

**Step 6: Commit**

```bash
git add apps/accounts/ templates/accounts/
git commit -m "feat: add dashboard and team management views"
```

---

## Phase 3: Clients App

### Task 3.1: Client Model

**Files:**
- Create: `apps/clients/models.py`
- Create: `apps/clients/admin.py`

**Step 1: Create apps/clients/models.py**

```python
from django.db import models


class Client(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def project_count(self):
        return self.projects.count()
```

**Step 2: Create apps/clients/admin.py**

```python
from django.contrib import admin

from .models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'created_at')
    search_fields = ('name', 'email')
```

**Step 3: Commit**

```bash
git add apps/clients/
git commit -m "feat: add Client model"
```

---

### Task 3.2: Client Views and Templates

**Files:**
- Create: `apps/clients/urls.py`
- Create: `apps/clients/views.py`
- Create: `apps/clients/forms.py`
- Create: `templates/clients/client_list.html`
- Create: `templates/clients/client_form.html`
- Create: `templates/clients/client_detail.html`
- Create: `templates/clients/partials/client_card.html`

**Step 1: Create apps/clients/forms.py**

```python
from django import forms

from .models import Client


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['name', 'email', 'phone', 'address', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full border rounded px-3 py-2'}),
            'email': forms.EmailInput(attrs={'class': 'w-full border rounded px-3 py-2'}),
            'phone': forms.TextInput(attrs={'class': 'w-full border rounded px-3 py-2'}),
            'address': forms.Textarea(attrs={'class': 'w-full border rounded px-3 py-2', 'rows': 3}),
            'notes': forms.Textarea(attrs={'class': 'w-full border rounded px-3 py-2', 'rows': 4}),
        }
```

**Step 2: Create apps/clients/urls.py**

```python
from django.urls import path

from . import views

urlpatterns = [
    path('', views.client_list, name='client_list'),
    path('create/', views.client_create, name='client_create'),
    path('<int:pk>/', views.client_detail, name='client_detail'),
    path('<int:pk>/edit/', views.client_edit, name='client_edit'),
    path('<int:pk>/delete/', views.client_delete, name='client_delete'),
]
```

**Step 3: Create apps/clients/views.py**

```python
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect

from .forms import ClientForm
from .models import Client


@login_required
def client_list(request):
    clients = Client.objects.all()
    return render(request, 'clients/client_list.html', {'clients': clients})


@login_required
def client_create(request):
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save()
            if request.htmx:
                return render(request, 'clients/partials/client_card.html', {'client': client})
            return redirect('client_detail', pk=client.pk)
    else:
        form = ClientForm()
    return render(request, 'clients/client_form.html', {'form': form})


@login_required
def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk)
    return render(request, 'clients/client_detail.html', {'client': client})


@login_required
def client_edit(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            return redirect('client_detail', pk=client.pk)
    else:
        form = ClientForm(instance=client)
    return render(request, 'clients/client_form.html', {'form': form, 'client': client})


@login_required
def client_delete(request, pk):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        client.delete()
        if request.htmx:
            return HttpResponse('')
        return redirect('client_list')
    return render(request, 'clients/client_confirm_delete.html', {'client': client})
```

**Step 4: Create templates/clients/client_list.html**

```html
{% extends "base.html" %}

{% block title %}Clients - WebFTL CRM{% endblock %}

{% block content %}
<div class="flex justify-between items-center mb-8">
    <h1 class="text-2xl font-bold">Clients</h1>
    <a href="{% url 'client_create' %}" class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
        Add Client
    </a>
</div>

<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" id="client-grid">
    {% for client in clients %}
    {% include "clients/partials/client_card.html" %}
    {% empty %}
    <div class="col-span-full text-center py-12 text-gray-500">
        No clients yet. <a href="{% url 'client_create' %}" class="text-blue-600 hover:underline">Add your first client</a>.
    </div>
    {% endfor %}
</div>
{% endblock %}
```

**Step 5: Create templates/clients/partials/client_card.html**

```html
<div class="bg-white rounded-lg shadow p-6" id="client-{{ client.pk }}">
    <a href="{% url 'client_detail' client.pk %}" class="block">
        <h3 class="font-semibold text-lg mb-2">{{ client.name }}</h3>
        {% if client.email %}
        <div class="text-sm text-gray-600 mb-1">{{ client.email }}</div>
        {% endif %}
        {% if client.phone %}
        <div class="text-sm text-gray-600 mb-2">{{ client.phone }}</div>
        {% endif %}
        <div class="text-sm text-gray-500">{{ client.project_count }} project{{ client.project_count|pluralize }}</div>
    </a>
</div>
```

**Step 6: Create templates/clients/client_form.html**

```html
{% extends "base.html" %}

{% block title %}{% if client %}Edit{% else %}New{% endif %} Client - WebFTL CRM{% endblock %}

{% block content %}
<div class="max-w-2xl">
    <h1 class="text-2xl font-bold mb-8">{% if client %}Edit {{ client.name }}{% else %}New Client{% endif %}</h1>

    <form method="post" class="bg-white rounded-lg shadow p-6 space-y-6">
        {% csrf_token %}

        {% for field in form %}
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ field.label }}</label>
            {{ field }}
            {% if field.errors %}
            <p class="text-red-500 text-sm mt-1">{{ field.errors.0 }}</p>
            {% endif %}
        </div>
        {% endfor %}

        <div class="flex gap-4">
            <button type="submit" class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
                {% if client %}Save Changes{% else %}Create Client{% endif %}
            </button>
            <a href="{% if client %}{% url 'client_detail' client.pk %}{% else %}{% url 'client_list' %}{% endif %}"
               class="px-4 py-2 text-gray-600 hover:underline">Cancel</a>
        </div>
    </form>
</div>
{% endblock %}
```

**Step 7: Create templates/clients/client_detail.html**

```html
{% extends "base.html" %}

{% block title %}{{ client.name }} - WebFTL CRM{% endblock %}

{% block content %}
<div class="flex justify-between items-start mb-8">
    <div>
        <a href="{% url 'client_list' %}" class="text-blue-600 hover:underline mb-2 block">&larr; All Clients</a>
        <h1 class="text-2xl font-bold">{{ client.name }}</h1>
    </div>
    <div class="flex gap-2">
        <a href="{% url 'client_edit' client.pk %}" class="bg-gray-100 px-4 py-2 rounded hover:bg-gray-200">Edit</a>
        {% if request.user.is_admin %}
        <button hx-delete="{% url 'client_delete' client.pk %}"
                hx-confirm="Delete {{ client.name }}? This will also delete all projects and tasks."
                hx-target="body"
                class="bg-red-100 text-red-600 px-4 py-2 rounded hover:bg-red-200">
            Delete
        </button>
        {% endif %}
    </div>
</div>

<div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
    <div class="lg:col-span-2">
        <div class="bg-white rounded-lg shadow p-6 mb-6">
            <h2 class="font-semibold mb-4">Contact Information</h2>
            <dl class="grid grid-cols-2 gap-4">
                <div>
                    <dt class="text-sm text-gray-500">Email</dt>
                    <dd>{{ client.email|default:"-" }}</dd>
                </div>
                <div>
                    <dt class="text-sm text-gray-500">Phone</dt>
                    <dd>{{ client.phone|default:"-" }}</dd>
                </div>
                <div class="col-span-2">
                    <dt class="text-sm text-gray-500">Address</dt>
                    <dd>{{ client.address|default:"-"|linebreaks }}</dd>
                </div>
            </dl>
        </div>

        {% if client.notes %}
        <div class="bg-white rounded-lg shadow p-6">
            <h2 class="font-semibold mb-4">Notes</h2>
            <div class="prose">{{ client.notes|linebreaks }}</div>
        </div>
        {% endif %}
    </div>

    <div>
        <div class="bg-white rounded-lg shadow p-6">
            <div class="flex justify-between items-center mb-4">
                <h2 class="font-semibold">Projects</h2>
                <a href="{% url 'project_create' %}?client={{ client.pk }}" class="text-blue-600 text-sm hover:underline">+ Add</a>
            </div>
            <div class="space-y-2">
                {% for project in client.projects.all %}
                <a href="{% url 'project_board' project.pk %}" class="block p-3 rounded hover:bg-gray-50 border">
                    {{ project.name }}
                </a>
                {% empty %}
                <div class="text-gray-500 text-sm">No projects yet</div>
                {% endfor %}
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

**Step 8: Commit**

```bash
git add apps/clients/ templates/clients/
git commit -m "feat: add client CRUD views and templates"
```

---

## Phase 4: Projects App

### Task 4.1: Project and Status Models

**Files:**
- Create: `apps/projects/models.py`
- Create: `apps/projects/admin.py`

**Step 1: Create apps/projects/models.py**

```python
from django.db import models

from apps.clients.models import Client


class Project(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='projects')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    github_repo_url = models.URLField(blank=True)
    github_sync_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.name} ({self.client.name})"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            self._create_default_statuses()

    def _create_default_statuses(self):
        defaults = ['Backlog', 'To Do', 'In Progress', 'Review', 'Done']
        for i, name in enumerate(defaults):
            Status.objects.create(project=self, name=name, order=i)


class Status(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='statuses')
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']
        verbose_name_plural = 'Statuses'

    def __str__(self):
        return self.name

    @property
    def task_count(self):
        return self.tasks.count()
```

**Step 2: Create apps/projects/admin.py**

```python
from django.contrib import admin

from .models import Project, Status


class StatusInline(admin.TabularInline):
    model = Status
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'client', 'github_sync_enabled', 'created_at')
    list_filter = ('client', 'github_sync_enabled')
    search_fields = ('name', 'client__name')
    inlines = [StatusInline]


@admin.register(Status)
class StatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'order')
    list_filter = ('project',)
```

**Step 3: Commit**

```bash
git add apps/projects/
git commit -m "feat: add Project and Status models"
```

---

### Task 4.2: Project Views and Kanban Board

**Files:**
- Create: `apps/projects/urls.py`
- Create: `apps/projects/views.py`
- Create: `apps/projects/forms.py`
- Create: `templates/projects/project_list.html`
- Create: `templates/projects/project_board.html`
- Create: `templates/projects/project_form.html`
- Create: `templates/projects/partials/kanban_column.html`
- Create: `templates/projects/partials/task_card.html`

**Step 1: Create apps/projects/forms.py**

```python
from django import forms

from .models import Project, Status


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['client', 'name', 'description', 'github_repo_url']
        widgets = {
            'client': forms.Select(attrs={'class': 'w-full border rounded px-3 py-2'}),
            'name': forms.TextInput(attrs={'class': 'w-full border rounded px-3 py-2'}),
            'description': forms.Textarea(attrs={'class': 'w-full border rounded px-3 py-2', 'rows': 4}),
            'github_repo_url': forms.URLInput(attrs={'class': 'w-full border rounded px-3 py-2', 'placeholder': 'https://github.com/org/repo'}),
        }


class StatusForm(forms.ModelForm):
    class Meta:
        model = Status
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full border rounded px-3 py-2'}),
        }
```

**Step 2: Create apps/projects/urls.py**

```python
from django.urls import path

from . import views

urlpatterns = [
    path('', views.project_list, name='project_list'),
    path('create/', views.project_create, name='project_create'),
    path('<int:pk>/', views.project_board, name='project_board'),
    path('<int:pk>/edit/', views.project_edit, name='project_edit'),
    path('<int:pk>/delete/', views.project_delete, name='project_delete'),
    path('<int:pk>/statuses/', views.manage_statuses, name='manage_statuses'),
    path('<int:pk>/statuses/reorder/', views.reorder_statuses, name='reorder_statuses'),
]
```

**Step 3: Create apps/projects/views.py**

```python
import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect

from .forms import ProjectForm, StatusForm
from .models import Project, Status
from apps.clients.models import Client


@login_required
def project_list(request):
    projects = Project.objects.select_related('client').all()
    client_filter = request.GET.get('client')
    if client_filter:
        projects = projects.filter(client_id=client_filter)
    clients = Client.objects.all()
    return render(request, 'projects/project_list.html', {
        'projects': projects,
        'clients': clients,
        'client_filter': client_filter,
    })


@login_required
def project_create(request):
    initial = {}
    if request.GET.get('client'):
        initial['client'] = request.GET.get('client')

    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save()
            return redirect('project_board', pk=project.pk)
    else:
        form = ProjectForm(initial=initial)
    return render(request, 'projects/project_form.html', {'form': form})


@login_required
def project_board(request, pk):
    project = get_object_or_404(
        Project.objects.prefetch_related('statuses__tasks__assignee', 'statuses__tasks__labels'),
        pk=pk
    )
    return render(request, 'projects/project_board.html', {'project': project})


@login_required
def project_edit(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            return redirect('project_board', pk=project.pk)
    else:
        form = ProjectForm(instance=project)
    return render(request, 'projects/project_form.html', {'form': form, 'project': project})


@login_required
def project_delete(request, pk):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        project.delete()
        return redirect('project_list')
    return render(request, 'projects/project_confirm_delete.html', {'project': project})


@login_required
def manage_statuses(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        form = StatusForm(request.POST)
        if form.is_valid():
            status = form.save(commit=False)
            status.project = project
            status.order = project.statuses.count()
            status.save()
            return render(request, 'projects/partials/kanban_column.html', {'status': status, 'project': project})
    return render(request, 'projects/manage_statuses.html', {'project': project})


@login_required
def reorder_statuses(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        order = json.loads(request.body).get('order', [])
        for i, status_id in enumerate(order):
            Status.objects.filter(pk=status_id, project=project).update(order=i)
        return HttpResponse(status=204)
    return HttpResponse(status=400)
```

**Step 4: Create templates/projects/project_list.html**

```html
{% extends "base.html" %}

{% block title %}Projects - WebFTL CRM{% endblock %}

{% block content %}
<div class="flex justify-between items-center mb-8">
    <h1 class="text-2xl font-bold">Projects</h1>
    <a href="{% url 'project_create' %}" class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
        New Project
    </a>
</div>

<div class="mb-6">
    <select onchange="window.location.href='?client=' + this.value" class="border rounded px-3 py-2">
        <option value="">All Clients</option>
        {% for client in clients %}
        <option value="{{ client.pk }}" {% if client_filter == client.pk|stringformat:"s" %}selected{% endif %}>
            {{ client.name }}
        </option>
        {% endfor %}
    </select>
</div>

<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
    {% for project in projects %}
    <a href="{% url 'project_board' project.pk %}" class="bg-white rounded-lg shadow p-6 hover:shadow-lg transition">
        <h3 class="font-semibold text-lg mb-1">{{ project.name }}</h3>
        <div class="text-sm text-gray-500 mb-3">{{ project.client.name }}</div>
        {% if project.description %}
        <p class="text-sm text-gray-600 line-clamp-2">{{ project.description }}</p>
        {% endif %}
    </a>
    {% empty %}
    <div class="col-span-full text-center py-12 text-gray-500">
        No projects yet. <a href="{% url 'project_create' %}" class="text-blue-600 hover:underline">Create your first project</a>.
    </div>
    {% endfor %}
</div>
{% endblock %}
```

**Step 5: Create templates/projects/project_board.html**

```html
{% extends "base.html" %}

{% block title %}{{ project.name }} - WebFTL CRM{% endblock %}

{% block content %}
<div class="flex justify-between items-start mb-6">
    <div>
        <a href="{% url 'project_list' %}" class="text-blue-600 hover:underline text-sm">&larr; All Projects</a>
        <h1 class="text-2xl font-bold">{{ project.name }}</h1>
        <div class="text-gray-500">{{ project.client.name }}</div>
    </div>
    <div class="flex gap-2">
        <button hx-get="{% url 'task_create' project.pk %}"
                hx-target="#slide-over"
                hx-swap="innerHTML"
                class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
            Add Task
        </button>
        <a href="{% url 'project_edit' project.pk %}" class="bg-gray-100 px-4 py-2 rounded hover:bg-gray-200">
            Settings
        </a>
    </div>
</div>

<div class="flex gap-4 overflow-x-auto pb-4"
     x-data="{ dragging: null }"
     id="kanban-board">
    {% for status in project.statuses.all %}
    {% include "projects/partials/kanban_column.html" %}
    {% endfor %}
</div>
{% endblock %}
```

**Step 6: Create templates/projects/partials/kanban_column.html**

```html
<div class="flex-shrink-0 w-80 bg-gray-100 rounded-lg p-4"
     id="column-{{ status.pk }}"
     @dragover.prevent="$el.classList.add('drag-over')"
     @dragleave="$el.classList.remove('drag-over')"
     @drop="$el.classList.remove('drag-over'); htmx.ajax('POST', '{% url 'task_move' %}', {values: {task_id: dragging, status_id: {{ status.pk }}}})">
    <div class="flex justify-between items-center mb-4">
        <h3 class="font-semibold">{{ status.name }}</h3>
        <span class="text-sm text-gray-500">{{ status.task_count }}</span>
    </div>
    <div class="space-y-3" id="column-{{ status.pk }}-tasks">
        {% for task in status.tasks.all %}
        {% include "projects/partials/task_card.html" %}
        {% endfor %}
    </div>
</div>
```

**Step 7: Create templates/projects/partials/task_card.html**

```html
<div class="bg-white rounded-lg shadow p-4 cursor-move"
     id="task-{{ task.pk }}"
     draggable="true"
     @dragstart="dragging = {{ task.pk }}; $el.classList.add('dragging')"
     @dragend="$el.classList.remove('dragging')"
     hx-get="{% url 'task_detail' task.pk %}"
     hx-target="#slide-over"
     hx-swap="innerHTML"
     hx-trigger="click">
    <div class="font-medium mb-2">{{ task.title }}</div>
    <div class="flex items-center gap-2 text-sm text-gray-500">
        {% if task.priority %}
        <span class="px-2 py-0.5 rounded text-xs
            {% if task.priority == 'urgent' %}bg-red-100 text-red-700
            {% elif task.priority == 'high' %}bg-orange-100 text-orange-700
            {% elif task.priority == 'medium' %}bg-yellow-100 text-yellow-700
            {% else %}bg-gray-100 text-gray-600{% endif %}">
            {{ task.get_priority_display }}
        </span>
        {% endif %}
        {% if task.assignee %}
        <span>{{ task.assignee.name }}</span>
        {% endif %}
        {% if task.due_date %}
        <span>{{ task.due_date|date:"M d" }}</span>
        {% endif %}
    </div>
    {% if task.labels.exists %}
    <div class="flex flex-wrap gap-1 mt-2">
        {% for label in task.labels.all %}
        <span class="px-2 py-0.5 text-xs rounded" style="background: {{ label.color }}20; color: {{ label.color }}">
            {{ label.name }}
        </span>
        {% endfor %}
    </div>
    {% endif %}
</div>
```

**Step 8: Create templates/projects/project_form.html**

```html
{% extends "base.html" %}

{% block title %}{% if project %}Edit{% else %}New{% endif %} Project - WebFTL CRM{% endblock %}

{% block content %}
<div class="max-w-2xl">
    <h1 class="text-2xl font-bold mb-8">{% if project %}Edit {{ project.name }}{% else %}New Project{% endif %}</h1>

    <form method="post" class="bg-white rounded-lg shadow p-6 space-y-6">
        {% csrf_token %}

        {% for field in form %}
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ field.label }}</label>
            {{ field }}
            {% if field.errors %}
            <p class="text-red-500 text-sm mt-1">{{ field.errors.0 }}</p>
            {% endif %}
        </div>
        {% endfor %}

        <div class="flex gap-4">
            <button type="submit" class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
                {% if project %}Save Changes{% else %}Create Project{% endif %}
            </button>
            <a href="{% if project %}{% url 'project_board' project.pk %}{% else %}{% url 'project_list' %}{% endif %}"
               class="px-4 py-2 text-gray-600 hover:underline">Cancel</a>
        </div>
    </form>
</div>
{% endblock %}
```

**Step 9: Commit**

```bash
git add apps/projects/ templates/projects/
git commit -m "feat: add project views and Kanban board"
```

---

## Phase 5: Tasks App

### Task 5.1: Task, Subtask, Comment, Label, Attachment Models

**Files:**
- Create: `apps/tasks/models.py`
- Create: `apps/tasks/admin.py`

**Step 1: Create apps/tasks/models.py**

```python
from django.conf import settings
from django.db import models

from apps.projects.models import Project, Status


class Label(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='labels')
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=7, default='#6366f1')  # Hex color

    class Meta:
        unique_together = ['project', 'name']

    def __str__(self):
        return self.name


class Task(models.Model):
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    status = models.ForeignKey(Status, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tasks'
    )
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, blank=True)
    due_date = models.DateField(null=True, blank=True)
    time_estimate = models.PositiveIntegerField(null=True, blank=True, help_text='Estimated hours')
    labels = models.ManyToManyField(Label, blank=True, related_name='tasks')
    order = models.PositiveIntegerField(default=0)

    # GitHub integration
    github_issue_id = models.PositiveIntegerField(null=True, blank=True)
    github_issue_number = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', '-created_at']

    def __str__(self):
        return self.title

    @property
    def subtask_progress(self):
        total = self.subtasks.count()
        if total == 0:
            return None
        completed = self.subtasks.filter(completed=True).count()
        return f"{completed}/{total}"


class Subtask(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='subtasks')
    title = models.CharField(max_length=255)
    completed = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.title


class Comment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.author} on {self.task}"


class Attachment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='attachments/%Y/%m/')
    filename = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.filename

    def save(self, *args, **kwargs):
        if not self.filename:
            self.filename = self.file.name
        super().save(*args, **kwargs)
```

**Step 2: Create apps/tasks/admin.py**

```python
from django.contrib import admin

from .models import Task, Subtask, Comment, Attachment, Label


class SubtaskInline(admin.TabularInline):
    model = Subtask
    extra = 0


class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0
    readonly_fields = ['author', 'created_at']


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'status', 'assignee', 'priority', 'due_date')
    list_filter = ('project', 'status', 'priority', 'assignee')
    search_fields = ('title', 'description')
    inlines = [SubtaskInline, CommentInline]


@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'color')
    list_filter = ('project',)
```

**Step 3: Commit**

```bash
git add apps/tasks/
git commit -m "feat: add Task, Subtask, Comment, Attachment models"
```

---

### Task 5.2: Task Views and Slide-Over Panel

**Files:**
- Create: `apps/tasks/urls.py`
- Create: `apps/tasks/views.py`
- Create: `apps/tasks/forms.py`
- Create: `templates/tasks/task_detail.html`
- Create: `templates/tasks/task_form.html`
- Create: `templates/tasks/my_tasks.html`
- Create: `templates/tasks/partials/subtask_item.html`
- Create: `templates/tasks/partials/comment_item.html`

**Step 1: Create apps/tasks/forms.py**

```python
from django import forms

from apps.accounts.models import User
from .models import Task, Subtask, Comment, Label


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['title', 'description', 'assignee', 'priority', 'due_date', 'time_estimate', 'labels']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'w-full border rounded px-3 py-2'}),
            'description': forms.Textarea(attrs={'class': 'w-full border rounded px-3 py-2', 'rows': 4}),
            'assignee': forms.Select(attrs={'class': 'w-full border rounded px-3 py-2'}),
            'priority': forms.Select(attrs={'class': 'w-full border rounded px-3 py-2'}),
            'due_date': forms.DateInput(attrs={'class': 'w-full border rounded px-3 py-2', 'type': 'date'}),
            'time_estimate': forms.NumberInput(attrs={'class': 'w-full border rounded px-3 py-2', 'placeholder': 'Hours'}),
            'labels': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, project=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assignee'].queryset = User.objects.filter(is_active=True)
        self.fields['assignee'].required = False
        if project:
            self.fields['labels'].queryset = Label.objects.filter(project=project)


class SubtaskForm(forms.ModelForm):
    class Meta:
        model = Subtask
        fields = ['title']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'w-full border rounded px-3 py-2', 'placeholder': 'Add subtask...'}),
        }


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={'class': 'w-full border rounded px-3 py-2', 'rows': 3, 'placeholder': 'Write a comment...'}),
        }
```

**Step 2: Create apps/tasks/urls.py**

```python
from django.urls import path

from . import views

urlpatterns = [
    path('my/', views.my_tasks, name='my_tasks'),
    path('move/', views.task_move, name='task_move'),
    path('project/<int:project_pk>/create/', views.task_create, name='task_create'),
    path('<int:pk>/', views.task_detail, name='task_detail'),
    path('<int:pk>/edit/', views.task_edit, name='task_edit'),
    path('<int:pk>/delete/', views.task_delete, name='task_delete'),
    path('<int:pk>/subtasks/', views.subtask_create, name='subtask_create'),
    path('<int:pk>/subtasks/<int:subtask_pk>/toggle/', views.subtask_toggle, name='subtask_toggle'),
    path('<int:pk>/subtasks/<int:subtask_pk>/delete/', views.subtask_delete, name='subtask_delete'),
    path('<int:pk>/comments/', views.comment_create, name='comment_create'),
    path('<int:pk>/attachments/', views.attachment_upload, name='attachment_upload'),
]
```

**Step 3: Create apps/tasks/views.py**

```python
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect

from apps.projects.models import Project, Status
from .forms import TaskForm, SubtaskForm, CommentForm
from .models import Task, Subtask, Attachment


@login_required
def my_tasks(request):
    tasks = Task.objects.filter(assignee=request.user).select_related('project', 'status')

    # Filters
    priority = request.GET.get('priority')
    if priority:
        tasks = tasks.filter(priority=priority)

    status_filter = request.GET.get('status')
    if status_filter:
        tasks = tasks.filter(status__name=status_filter)

    return render(request, 'tasks/my_tasks.html', {'tasks': tasks})


@login_required
def task_create(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk)
    status = project.statuses.first()  # Default to first status

    if request.method == 'POST':
        form = TaskForm(project, request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.project = project
            task.status = status
            task.save()
            form.save_m2m()
            if request.htmx:
                return render(request, 'projects/partials/task_card.html', {'task': task})
            return redirect('project_board', pk=project.pk)
    else:
        form = TaskForm(project)

    return render(request, 'tasks/task_form.html', {'form': form, 'project': project})


@login_required
def task_detail(request, pk):
    task = get_object_or_404(
        Task.objects.select_related('project', 'status', 'assignee')
        .prefetch_related('subtasks', 'comments__author', 'attachments', 'labels'),
        pk=pk
    )
    subtask_form = SubtaskForm()
    comment_form = CommentForm()
    return render(request, 'tasks/task_detail.html', {
        'task': task,
        'subtask_form': subtask_form,
        'comment_form': comment_form,
    })


@login_required
def task_edit(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if request.method == 'POST':
        form = TaskForm(task.project, request.POST, instance=task)
        if form.is_valid():
            form.save()
            if request.htmx:
                return render(request, 'tasks/task_detail.html', {'task': task})
            return redirect('project_board', pk=task.project.pk)
    else:
        form = TaskForm(task.project, instance=task)
    return render(request, 'tasks/task_form.html', {'form': form, 'task': task, 'project': task.project})


@login_required
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk)
    project_pk = task.project.pk
    if request.method == 'POST':
        task.delete()
        if request.htmx:
            return HttpResponse('')
        return redirect('project_board', pk=project_pk)
    return HttpResponse(status=405)


@login_required
def task_move(request):
    if request.method == 'POST':
        task_id = request.POST.get('task_id')
        status_id = request.POST.get('status_id')
        task = get_object_or_404(Task, pk=task_id)
        status = get_object_or_404(Status, pk=status_id, project=task.project)
        task.status = status
        task.save()
        return render(request, 'projects/partials/task_card.html', {'task': task})
    return HttpResponse(status=400)


@login_required
def subtask_create(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if request.method == 'POST':
        form = SubtaskForm(request.POST)
        if form.is_valid():
            subtask = form.save(commit=False)
            subtask.task = task
            subtask.order = task.subtasks.count()
            subtask.save()
            return render(request, 'tasks/partials/subtask_item.html', {'subtask': subtask})
    return HttpResponse(status=400)


@login_required
def subtask_toggle(request, pk, subtask_pk):
    subtask = get_object_or_404(Subtask, pk=subtask_pk, task_id=pk)
    subtask.completed = not subtask.completed
    subtask.save()
    return render(request, 'tasks/partials/subtask_item.html', {'subtask': subtask})


@login_required
def subtask_delete(request, pk, subtask_pk):
    subtask = get_object_or_404(Subtask, pk=subtask_pk, task_id=pk)
    subtask.delete()
    return HttpResponse('')


@login_required
def comment_create(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if request.method == 'POST':
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.task = task
            comment.author = request.user
            comment.save()
            return render(request, 'tasks/partials/comment_item.html', {'comment': comment})
    return HttpResponse(status=400)


@login_required
def attachment_upload(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if request.method == 'POST' and request.FILES.get('file'):
        file = request.FILES['file']
        attachment = Attachment.objects.create(
            task=task,
            file=file,
            filename=file.name,
            uploaded_by=request.user
        )
        return render(request, 'tasks/partials/attachment_item.html', {'attachment': attachment})
    return HttpResponse(status=400)
```

**Step 4: Create templates/tasks/task_detail.html**

```html
<div class="slide-over-panel p-6" x-data="{ editing: false }">
    <div class="flex justify-between items-start mb-6">
        <div class="flex-1">
            <h2 class="text-xl font-bold" x-show="!editing">{{ task.title }}</h2>
            <div class="text-sm text-gray-500 mt-1">
                {{ task.project.name }} &middot; {{ task.status.name }}
            </div>
        </div>
        <div class="flex gap-2">
            <button @click="editing = !editing" class="text-gray-500 hover:text-gray-700">
                <span x-text="editing ? 'Cancel' : 'Edit'"></span>
            </button>
            <button onclick="document.getElementById('slide-over').classList.add('hidden')"
                    class="text-gray-500 hover:text-gray-700">&times;</button>
        </div>
    </div>

    <div x-show="!editing" class="space-y-6">
        <!-- Meta info -->
        <div class="grid grid-cols-2 gap-4 text-sm">
            <div>
                <span class="text-gray-500">Assignee</span>
                <div>{{ task.assignee.name|default:"Unassigned" }}</div>
            </div>
            <div>
                <span class="text-gray-500">Priority</span>
                <div>{{ task.get_priority_display|default:"None" }}</div>
            </div>
            <div>
                <span class="text-gray-500">Due Date</span>
                <div>{{ task.due_date|date:"M d, Y"|default:"None" }}</div>
            </div>
            <div>
                <span class="text-gray-500">Estimate</span>
                <div>{% if task.time_estimate %}{{ task.time_estimate }}h{% else %}None{% endif %}</div>
            </div>
        </div>

        <!-- Labels -->
        {% if task.labels.exists %}
        <div class="flex flex-wrap gap-1">
            {% for label in task.labels.all %}
            <span class="px-2 py-1 text-sm rounded" style="background: {{ label.color }}20; color: {{ label.color }}">
                {{ label.name }}
            </span>
            {% endfor %}
        </div>
        {% endif %}

        <!-- Description -->
        {% if task.description %}
        <div>
            <h3 class="font-semibold mb-2">Description</h3>
            <div class="prose text-sm">{{ task.description|linebreaks }}</div>
        </div>
        {% endif %}

        <!-- Subtasks -->
        <div>
            <h3 class="font-semibold mb-2">Subtasks {% if task.subtask_progress %}({{ task.subtask_progress }}){% endif %}</h3>
            <div id="subtask-list" class="space-y-2 mb-3">
                {% for subtask in task.subtasks.all %}
                {% include "tasks/partials/subtask_item.html" %}
                {% endfor %}
            </div>
            <form hx-post="{% url 'subtask_create' task.pk %}" hx-target="#subtask-list" hx-swap="beforeend">
                {% csrf_token %}
                {{ subtask_form.title }}
            </form>
        </div>

        <!-- Attachments -->
        <div>
            <h3 class="font-semibold mb-2">Attachments</h3>
            <div id="attachment-list" class="space-y-2 mb-3">
                {% for attachment in task.attachments.all %}
                {% include "tasks/partials/attachment_item.html" %}
                {% endfor %}
            </div>
            <form hx-post="{% url 'attachment_upload' task.pk %}"
                  hx-target="#attachment-list"
                  hx-swap="beforeend"
                  hx-encoding="multipart/form-data">
                {% csrf_token %}
                <input type="file" name="file" class="text-sm">
            </form>
        </div>

        <!-- Comments -->
        <div>
            <h3 class="font-semibold mb-2">Comments</h3>
            <div id="comment-list" class="space-y-4 mb-4">
                {% for comment in task.comments.all %}
                {% include "tasks/partials/comment_item.html" %}
                {% endfor %}
            </div>
            <form hx-post="{% url 'comment_create' task.pk %}" hx-target="#comment-list" hx-swap="beforeend">
                {% csrf_token %}
                {{ comment_form.content }}
                <button type="submit" class="mt-2 bg-blue-600 text-white px-4 py-2 rounded text-sm">
                    Add Comment
                </button>
            </form>
        </div>

        <!-- GitHub Info -->
        {% if task.github_issue_number %}
        <div class="border-t pt-4">
            <h3 class="font-semibold mb-2">GitHub</h3>
            <a href="{{ task.project.github_repo_url }}/issues/{{ task.github_issue_number }}"
               target="_blank"
               class="text-blue-600 hover:underline">
                Issue #{{ task.github_issue_number }}
            </a>
        </div>
        {% endif %}

        <!-- Delete -->
        <div class="border-t pt-4">
            <button hx-delete="{% url 'task_delete' task.pk %}"
                    hx-confirm="Delete this task?"
                    hx-target="#task-{{ task.pk }}"
                    hx-swap="delete"
                    @click="document.getElementById('slide-over').classList.add('hidden')"
                    class="text-red-600 text-sm hover:underline">
                Delete Task
            </button>
        </div>
    </div>

    <!-- Edit form -->
    <div x-show="editing" x-cloak>
        <form hx-post="{% url 'task_edit' task.pk %}" hx-target="#slide-over" hx-swap="innerHTML">
            {% csrf_token %}
            {% include "tasks/task_form_fields.html" %}
            <button type="submit" class="bg-blue-600 text-white px-4 py-2 rounded mt-4">Save</button>
        </form>
    </div>
</div>

<script>
    document.getElementById('slide-over').classList.remove('hidden');
</script>
```

**Step 5: Create templates/tasks/partials/subtask_item.html**

```html
<div class="flex items-center gap-2" id="subtask-{{ subtask.pk }}">
    <input type="checkbox"
           {% if subtask.completed %}checked{% endif %}
           hx-post="{% url 'subtask_toggle' subtask.task.pk subtask.pk %}"
           hx-target="#subtask-{{ subtask.pk }}"
           hx-swap="outerHTML"
           class="rounded">
    <span class="flex-1 {% if subtask.completed %}line-through text-gray-400{% endif %}">
        {{ subtask.title }}
    </span>
    <button hx-delete="{% url 'subtask_delete' subtask.task.pk subtask.pk %}"
            hx-target="#subtask-{{ subtask.pk }}"
            hx-swap="delete"
            class="text-gray-400 hover:text-red-500">&times;</button>
</div>
```

**Step 6: Create templates/tasks/partials/comment_item.html**

```html
<div class="border-l-2 border-gray-200 pl-4">
    <div class="flex items-center gap-2 mb-1">
        <span class="font-medium text-sm">{{ comment.author.name }}</span>
        <span class="text-gray-400 text-xs">{{ comment.created_at|timesince }} ago</span>
    </div>
    <div class="text-sm">{{ comment.content|linebreaks }}</div>
</div>
```

**Step 7: Create templates/tasks/partials/attachment_item.html**

```html
<div class="flex items-center gap-2 text-sm">
    <a href="{{ attachment.file.url }}" target="_blank" class="text-blue-600 hover:underline flex-1">
        {{ attachment.filename }}
    </a>
    <span class="text-gray-400">{{ attachment.uploaded_at|date:"M d" }}</span>
</div>
```

**Step 8: Create templates/tasks/task_form.html**

```html
{% extends "base.html" %}

{% block title %}{% if task %}Edit Task{% else %}New Task{% endif %} - WebFTL CRM{% endblock %}

{% block content %}
<div class="max-w-2xl">
    <h1 class="text-2xl font-bold mb-8">{% if task %}Edit Task{% else %}New Task{% endif %}</h1>

    <form method="post" class="bg-white rounded-lg shadow p-6 space-y-6">
        {% csrf_token %}
        {% include "tasks/task_form_fields.html" %}

        <div class="flex gap-4">
            <button type="submit" class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
                {% if task %}Save{% else %}Create{% endif %}
            </button>
            <a href="{% url 'project_board' project.pk %}" class="px-4 py-2 text-gray-600 hover:underline">Cancel</a>
        </div>
    </form>
</div>
{% endblock %}
```

**Step 9: Create templates/tasks/task_form_fields.html**

```html
{% for field in form %}
<div>
    <label class="block text-sm font-medium text-gray-700 mb-1">{{ field.label }}</label>
    {{ field }}
    {% if field.errors %}
    <p class="text-red-500 text-sm mt-1">{{ field.errors.0 }}</p>
    {% endif %}
</div>
{% endfor %}
```

**Step 10: Create templates/tasks/my_tasks.html**

```html
{% extends "base.html" %}

{% block title %}My Tasks - WebFTL CRM{% endblock %}

{% block content %}
<div class="flex justify-between items-center mb-8">
    <h1 class="text-2xl font-bold">My Tasks</h1>
</div>

<div class="mb-6 flex gap-4">
    <select onchange="window.location.href='?priority=' + this.value" class="border rounded px-3 py-2">
        <option value="">All Priorities</option>
        <option value="urgent" {% if request.GET.priority == "urgent" %}selected{% endif %}>Urgent</option>
        <option value="high" {% if request.GET.priority == "high" %}selected{% endif %}>High</option>
        <option value="medium" {% if request.GET.priority == "medium" %}selected{% endif %}>Medium</option>
        <option value="low" {% if request.GET.priority == "low" %}selected{% endif %}>Low</option>
    </select>
</div>

<div class="bg-white rounded-lg shadow">
    <table class="w-full">
        <thead class="bg-gray-50">
            <tr>
                <th class="px-6 py-3 text-left text-sm font-semibold">Task</th>
                <th class="px-6 py-3 text-left text-sm font-semibold">Project</th>
                <th class="px-6 py-3 text-left text-sm font-semibold">Status</th>
                <th class="px-6 py-3 text-left text-sm font-semibold">Priority</th>
                <th class="px-6 py-3 text-left text-sm font-semibold">Due</th>
            </tr>
        </thead>
        <tbody class="divide-y">
            {% for task in tasks %}
            <tr class="hover:bg-gray-50 cursor-pointer"
                hx-get="{% url 'task_detail' task.pk %}"
                hx-target="#slide-over"
                hx-swap="innerHTML">
                <td class="px-6 py-4">{{ task.title }}</td>
                <td class="px-6 py-4 text-gray-500">{{ task.project.name }}</td>
                <td class="px-6 py-4">
                    <span class="px-2 py-1 text-xs rounded bg-gray-100">{{ task.status.name }}</span>
                </td>
                <td class="px-6 py-4">
                    {% if task.priority %}
                    <span class="px-2 py-1 text-xs rounded
                        {% if task.priority == 'urgent' %}bg-red-100 text-red-700
                        {% elif task.priority == 'high' %}bg-orange-100 text-orange-700
                        {% elif task.priority == 'medium' %}bg-yellow-100 text-yellow-700
                        {% else %}bg-gray-100{% endif %}">
                        {{ task.get_priority_display }}
                    </span>
                    {% endif %}
                </td>
                <td class="px-6 py-4 text-gray-500">{{ task.due_date|date:"M d"|default:"-" }}</td>
            </tr>
            {% empty %}
            <tr>
                <td colspan="5" class="px-6 py-12 text-center text-gray-500">No tasks assigned to you yet.</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
```

**Step 11: Commit**

```bash
git add apps/tasks/ templates/tasks/
git commit -m "feat: add task views, slide-over panel, subtasks, comments"
```

---

## Phase 6: GitHub Integration

### Task 6.1: GitHub Integration Models and Helpers

**Files:**
- Create: `apps/integrations/__init__.py`
- Create: `apps/integrations/models.py`
- Create: `apps/integrations/github.py`
- Create: `apps/integrations/admin.py`

**Step 1: Create apps/integrations/models.py**

```python
from django.db import models

from apps.tasks.models import Task


class GitHubCommit(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='commits')
    sha = models.CharField(max_length=40, unique=True)
    message = models.TextField()
    author = models.CharField(max_length=255)
    url = models.URLField()
    created_at = models.DateTimeField()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.sha[:7]} - {self.message[:50]}"


class GitHubPullRequest(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('closed', 'Closed'),
        ('merged', 'Merged'),
    ]

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='pull_requests')
    number = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    url = models.URLField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        ordering = ['-updated_at']
        unique_together = ['task', 'number']

    def __str__(self):
        return f"#{self.number} - {self.title}"
```

**Step 2: Create apps/integrations/github.py**

```python
import re
from datetime import datetime

import httpx

from apps.projects.models import Project
from apps.tasks.models import Task
from .models import GitHubCommit, GitHubPullRequest


def parse_repo_url(url: str) -> tuple[str, str] | None:
    """Extract owner and repo from GitHub URL."""
    match = re.match(r'https?://github\.com/([^/]+)/([^/]+)', url)
    if match:
        return match.group(1), match.group(2).rstrip('.git')
    return None


def get_github_headers(token: str) -> dict:
    return {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }


async def sync_issues_from_github(project: Project, token: str):
    """Sync issues from GitHub to tasks."""
    repo_info = parse_repo_url(project.github_repo_url)
    if not repo_info:
        return

    owner, repo = repo_info
    url = f'https://api.github.com/repos/{owner}/{repo}/issues'

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=get_github_headers(token))
        if response.status_code != 200:
            return

        issues = response.json()
        backlog = project.statuses.first()

        for issue in issues:
            if 'pull_request' in issue:
                continue  # Skip PRs

            Task.objects.update_or_create(
                project=project,
                github_issue_id=issue['id'],
                defaults={
                    'github_issue_number': issue['number'],
                    'title': issue['title'],
                    'description': issue['body'] or '',
                    'status': backlog,
                }
            )


async def create_github_issue(task: Task, token: str):
    """Create GitHub issue from task."""
    if not task.project.github_repo_url:
        return None

    repo_info = parse_repo_url(task.project.github_repo_url)
    if not repo_info:
        return None

    owner, repo = repo_info
    url = f'https://api.github.com/repos/{owner}/{repo}/issues'

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            headers=get_github_headers(token),
            json={
                'title': task.title,
                'body': task.description,
            }
        )
        if response.status_code == 201:
            data = response.json()
            task.github_issue_id = data['id']
            task.github_issue_number = data['number']
            task.save()
            return data
    return None


def extract_task_id_from_message(message: str) -> int | None:
    """Extract task ID from commit message like 'fix: update #TASK-123'."""
    match = re.search(r'#TASK-(\d+)', message)
    if match:
        return int(match.group(1))
    return None


def process_webhook_push(payload: dict, project: Project):
    """Process push webhook and link commits to tasks."""
    for commit in payload.get('commits', []):
        task_id = extract_task_id_from_message(commit['message'])
        if not task_id:
            continue

        try:
            task = Task.objects.get(pk=task_id, project=project)
            GitHubCommit.objects.update_or_create(
                sha=commit['id'],
                defaults={
                    'task': task,
                    'message': commit['message'],
                    'author': commit['author']['name'],
                    'url': commit['url'],
                    'created_at': datetime.fromisoformat(commit['timestamp'].replace('Z', '+00:00')),
                }
            )
        except Task.DoesNotExist:
            pass


def process_webhook_issue(payload: dict, project: Project):
    """Process issue webhook events."""
    action = payload.get('action')
    issue = payload.get('issue', {})

    if action == 'opened':
        backlog = project.statuses.first()
        Task.objects.update_or_create(
            project=project,
            github_issue_id=issue['id'],
            defaults={
                'github_issue_number': issue['number'],
                'title': issue['title'],
                'description': issue['body'] or '',
                'status': backlog,
            }
        )
    elif action == 'closed':
        try:
            task = Task.objects.get(project=project, github_issue_id=issue['id'])
            done_status = project.statuses.filter(name='Done').first()
            if done_status:
                task.status = done_status
                task.save()
        except Task.DoesNotExist:
            pass
    elif action == 'edited':
        try:
            task = Task.objects.get(project=project, github_issue_id=issue['id'])
            task.title = issue['title']
            task.description = issue['body'] or ''
            task.save()
        except Task.DoesNotExist:
            pass


def process_webhook_pull_request(payload: dict, project: Project):
    """Process PR webhook and link to tasks."""
    pr = payload.get('pull_request', {})
    body = pr.get('body', '') or ''

    # Look for task references in PR body
    task_id = extract_task_id_from_message(body)
    if not task_id:
        task_id = extract_task_id_from_message(pr.get('title', ''))

    if not task_id:
        return

    try:
        task = Task.objects.get(pk=task_id, project=project)
        status = 'merged' if pr.get('merged') else pr.get('state', 'open')

        GitHubPullRequest.objects.update_or_create(
            task=task,
            number=pr['number'],
            defaults={
                'title': pr['title'],
                'status': status,
                'url': pr['html_url'],
                'created_at': datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')),
                'updated_at': datetime.fromisoformat(pr['updated_at'].replace('Z', '+00:00')),
            }
        )
    except Task.DoesNotExist:
        pass
```

**Step 3: Create apps/integrations/admin.py**

```python
from django.contrib import admin

from .models import GitHubCommit, GitHubPullRequest


@admin.register(GitHubCommit)
class GitHubCommitAdmin(admin.ModelAdmin):
    list_display = ('sha', 'task', 'author', 'created_at')
    list_filter = ('task__project',)
    search_fields = ('sha', 'message')


@admin.register(GitHubPullRequest)
class GitHubPullRequestAdmin(admin.ModelAdmin):
    list_display = ('number', 'title', 'task', 'status', 'updated_at')
    list_filter = ('status', 'task__project')
```

**Step 4: Commit**

```bash
git add apps/integrations/
git commit -m "feat: add GitHub integration models and helpers"
```

---

### Task 6.2: GitHub Webhook Endpoint

**Files:**
- Create: `apps/integrations/urls.py`
- Create: `apps/integrations/views.py`

**Step 1: Create apps/integrations/urls.py**

```python
from django.urls import path

from . import views

urlpatterns = [
    path('github/webhook/', views.github_webhook, name='github_webhook'),
    path('github/sync/<int:project_pk>/', views.github_sync, name='github_sync'),
]
```

**Step 2: Create apps/integrations/views.py**

```python
import hashlib
import hmac
import json

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404

from apps.projects.models import Project
from .github import (
    process_webhook_push,
    process_webhook_issue,
    process_webhook_pull_request,
)


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature."""
    if not signature or not secret:
        return False
    expected = 'sha256=' + hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@csrf_exempt
@require_POST
def github_webhook(request):
    """Handle GitHub webhook events."""
    signature = request.headers.get('X-Hub-Signature-256', '')
    event = request.headers.get('X-GitHub-Event', '')

    # Get webhook secret from settings (optional for dev)
    webhook_secret = getattr(settings, 'GITHUB_WEBHOOK_SECRET', '')

    if webhook_secret and not verify_signature(request.body, signature, webhook_secret):
        return HttpResponse('Invalid signature', status=401)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse('Invalid JSON', status=400)

    # Find project by repository URL
    repo_url = payload.get('repository', {}).get('html_url', '')
    if not repo_url:
        return HttpResponse('No repository URL', status=400)

    try:
        project = Project.objects.get(
            github_repo_url__icontains=repo_url.replace('https://github.com/', ''),
            github_sync_enabled=True
        )
    except Project.DoesNotExist:
        return HttpResponse('Project not found or sync disabled', status=404)

    if event == 'push':
        process_webhook_push(payload, project)
    elif event == 'issues':
        process_webhook_issue(payload, project)
    elif event == 'pull_request':
        process_webhook_pull_request(payload, project)

    return HttpResponse('OK')


@login_required
@require_POST
def github_sync(request, project_pk):
    """Manually trigger GitHub sync for a project."""
    project = get_object_or_404(Project, pk=project_pk)

    if not project.github_repo_url:
        return JsonResponse({'error': 'No GitHub repo configured'}, status=400)

    if not request.user.github_token:
        return JsonResponse({'error': 'GitHub token not configured'}, status=400)

    # For MVP, we'll do sync synchronously
    # In production, use Celery/Django-Q
    import asyncio
    from .github import sync_issues_from_github

    asyncio.run(sync_issues_from_github(project, request.user.github_token))

    return JsonResponse({'status': 'synced'})
```

**Step 3: Commit**

```bash
git add apps/integrations/
git commit -m "feat: add GitHub webhook endpoint"
```

---

## Phase 7: Final Setup

### Task 7.1: Create Migrations and Test Setup

**Files:**
- Modify: `config/settings.py` (add test settings)

**Step 1: Install dependencies in venv**

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

**Step 2: Start PostgreSQL and run migrations**

```bash
docker-compose up -d  # Start PostgreSQL
source .venv/bin/activate
python manage.py makemigrations accounts clients projects tasks integrations
python manage.py migrate
python manage.py createsuperuser
```

**Step 3: Add GITHUB_WEBHOOK_SECRET to settings**

Add to `config/settings.py`:

```python
# GitHub
GITHUB_WEBHOOK_SECRET = os.getenv('GITHUB_WEBHOOK_SECRET', '')
```

**Step 4: Add to .env.example**

```
GITHUB_WEBHOOK_SECRET=your-webhook-secret-here
```

**Step 5: Verify the app runs**

```bash
docker-compose up -d  # Ensure PostgreSQL is running
source .venv/bin/activate
python manage.py runserver
```

Visit http://localhost:8000 and:
1. Create an account
2. Create a client
3. Create a project
4. Add tasks to the Kanban board
5. Test drag-drop
6. Test task detail slide-over

**Step 6: Commit**

```bash
git add .
git commit -m "feat: complete MVP setup with migrations"
```

---

## Summary

**Phases completed:**
1. Project Foundation (venv, PostgreSQL Docker, Django, templates)
2. Accounts App (User model, roles, team)
3. Clients App (CRUD)
4. Projects App (CRUD, Kanban, statuses)
5. Tasks App (CRUD, subtasks, comments, attachments)
6. GitHub Integration (webhooks, sync)
7. Final Setup (migrations, testing)

**Key Features Implemented:**
- Email/password auth with django-allauth
- Admin/Member roles
- Client management (basic info)
- Project management with customizable statuses
- Kanban board with drag-drop (HTMX + Alpine.js)
- Task details in slide-over panel
- Subtasks, comments, attachments
- GitHub issue sync (bidirectional)
- PR/commit tracking via webhooks
- My Tasks view with filters

**Not Yet Implemented (Post-MVP):**
- Invoicing, estimates, payments
- Time tracking
- Support tickets
- Client portal
- Notifications
- Custom fields
- Reporting
