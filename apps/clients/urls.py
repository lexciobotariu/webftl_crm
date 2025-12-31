from django.urls import path

from . import views

urlpatterns = [
    path('', views.client_list, name='client_list'),
    path('create/', views.client_create, name='client_create'),
    path('<int:pk>/', views.client_detail, name='client_detail'),
    path('<int:pk>/edit/', views.client_edit, name='client_edit'),
    path('<int:pk>/edit/drawer/', views.client_edit_drawer, name='client_edit_drawer'),
    path('<int:pk>/notes/', views.client_notes_display, name='client_notes_display'),
    path('<int:pk>/notes/edit/', views.client_edit_notes, name='client_edit_notes'),
    path('<int:pk>/delete/', views.client_delete, name='client_delete'),
]
