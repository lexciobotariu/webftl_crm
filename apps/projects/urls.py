from django.urls import path

from . import views

urlpatterns = [
    path('', views.project_list, name='project_list'),
    path('create/', views.project_create, name='project_create'),
    path('<int:pk>/', views.project_board, name='project_board'),
    path('<int:pk>/edit/', views.project_edit, name='project_edit'),
    path('<int:pk>/delete/', views.project_delete, name='project_delete'),
    path('<int:pk>/settings/', views.project_settings, name='project_settings'),
    path('<int:pk>/statuses/', views.manage_statuses, name='manage_statuses'),
    path('<int:pk>/statuses/reorder/', views.reorder_statuses, name='reorder_statuses'),
    path('<int:pk>/labels/create/', views.label_create, name='label_create'),
    path('<int:pk>/labels/<int:label_pk>/delete/', views.label_delete, name='label_delete'),
]
