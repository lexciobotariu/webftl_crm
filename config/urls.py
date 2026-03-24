from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from apps.todos import views as todo_views
from config import views as config_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('changelog/', config_views.changelog_view, name='changelog'),
    path('accounts/', include('allauth.urls')),
    path('', include('apps.accounts.urls')),
    path('clients/', include('apps.clients.urls')),
    path('clients/<int:pk>/todos/', include([
        # Use a sub-path to avoid colliding with the client detail "todos" tab route.
        path('list/', todo_views.client_todo_list, name='client_todo_list'),
        path('create/', todo_views.client_todo_create, name='client_todo_create'),
    ])),
    path('projects/', include('apps.projects.urls')),
    path('tasks/', include('apps.tasks.urls')),
    path('todos/', include('apps.todos.urls')),
    path('integrations/', include('apps.integrations.urls')),
    path('notes/', include('apps.notes.urls')),
    path('salaries/', include('apps.salaries.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
