from django.urls import path

from . import views

urlpatterns = [
    path('my/', views.my_tasks, name='my_tasks'),
    path('move/', views.task_move, name='task_move'),
    path('project/<int:project_pk>/create/', views.task_create, name='task_create'),
    path('<int:pk>/', views.task_detail, name='task_detail'),
    path('<int:pk>/edit/', views.task_edit, name='task_edit'),
    path('<int:pk>/status/', views.task_update_status, name='task_update_status'),
    path('<int:pk>/delete/', views.task_delete, name='task_delete'),
    path('<int:pk>/subtasks/', views.subtask_create, name='subtask_create'),
    path('<int:pk>/subtasks/<int:subtask_pk>/toggle/', views.subtask_toggle, name='subtask_toggle'),
    path('<int:pk>/subtasks/<int:subtask_pk>/delete/', views.subtask_delete, name='subtask_delete'),
    path('<int:pk>/comments/', views.comment_create, name='comment_create'),
    path('<int:pk>/attachments/', views.attachment_upload, name='attachment_upload'),
    # Full page task view
    path('project/<int:project_pk>/<int:task_pk>/', views.task_full_page, name='task_full_page'),
    # Property update endpoints
    path('<int:pk>/assignee/', views.task_update_assignee, name='task_update_assignee'),
    path('<int:pk>/priority/', views.task_update_priority, name='task_update_priority'),
    path('<int:pk>/due-date/', views.task_update_due_date, name='task_update_due_date'),
    path('<int:pk>/estimate/', views.task_update_estimate, name='task_update_estimate'),
    path('<int:pk>/labels/<int:label_pk>/toggle/', views.task_toggle_label, name='task_toggle_label'),
    path('<int:pk>/description/', views.task_edit_description, name='task_edit_description'),
    path('<int:pk>/title/', views.task_edit_title, name='task_edit_title'),
]
