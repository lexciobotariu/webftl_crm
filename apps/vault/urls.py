from django.urls import path

from . import views

urlpatterns = [
    path('client/<int:client_pk>/', views.vault_list, name='vault_list'),
    path('client/<int:client_pk>/new/', views.vault_create, name='vault_create'),
    path('<int:pk>/edit/', views.vault_edit, name='vault_edit'),
    path('<int:pk>/delete/', views.vault_delete, name='vault_delete'),
    path('<int:pk>/show/', views.vault_reveal, name='vault_reveal'),
    path('<int:pk>/copy/', views.vault_copy, name='vault_copy'),
]
