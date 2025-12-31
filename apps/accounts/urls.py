from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('team/', views.team_list, name='team_list'),
    path('team/<int:pk>/toggle-role/', views.toggle_role, name='toggle_role'),
]
