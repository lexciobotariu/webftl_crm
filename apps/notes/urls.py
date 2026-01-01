from django.urls import path
from . import views

urlpatterns = [
    # Client notes
    path('client/<int:client_pk>/create/drawer/', views.note_create_drawer, name='client_note_create_drawer'),
    path('client/<int:client_pk>/list/', views.client_notes_list, name='client_notes_list'),

    # Project notes
    path('project/<int:project_pk>/create/drawer/', views.note_create_drawer, name='project_note_create_drawer'),
    path('project/<int:project_pk>/list/', views.project_notes_list, name='project_notes_list'),

    # Note operations (works for both client and project notes)
    path('<int:pk>/', views.note_detail_drawer, name='note_detail_drawer'),
    path('<int:pk>/edit/', views.note_edit_drawer, name='note_edit_drawer'),
    path('<int:pk>/delete/', views.note_delete, name='note_delete'),
]
