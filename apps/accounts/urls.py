from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('team/', views.team_list, name='team_list'),
    path('team/create/', views.user_create, name='user_create'),
    path('team/<int:pk>/update/', views.user_update, name='user_update'),
    path('team/<int:pk>/deactivate/', views.user_deactivate, name='user_deactivate'),
    path('team/<int:pk>/detail/', views.user_detail_drawer, name='user_detail_drawer'),
    path('team/presets/', views.preset_list, name='preset_list'),
    path('team/presets/create/', views.preset_create, name='preset_create'),
    path('team/presets/<int:pk>/edit/', views.preset_edit, name='preset_edit'),
    path('team/presets/<int:pk>/delete/', views.preset_delete, name='preset_delete'),
    path('team/<int:pk>/delete-confirm/', views.user_delete_confirm, name='user_delete_confirm'),
    path('team/<int:pk>/delete/', views.user_delete, name='user_delete'),
]
