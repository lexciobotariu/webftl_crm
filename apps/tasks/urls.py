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
