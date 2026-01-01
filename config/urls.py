from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from apps.todos import views as todo_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', include('apps.accounts.urls')),
    path('clients/', include('apps.clients.urls')),
    path('clients/<int:pk>/todos/', include([
        path('', todo_views.client_todo_list, name='client_todo_list'),
        path('create/', todo_views.client_todo_create, name='client_todo_create'),
    ])),
    path('projects/', include('apps.projects.urls')),
    path('tasks/', include('apps.tasks.urls')),
    path('todos/', include('apps.todos.urls')),
    path('integrations/', include('apps.integrations.urls')),
    path('notes/', include('apps.notes.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
