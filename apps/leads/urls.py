from django.urls import path

from . import views

urlpatterns = [
    path('', views.lead_list, name='lead_list'),
    path('new/', views.lead_create, name='lead_create'),
    path('<int:pk>/', views.lead_detail, name='lead_detail'),
    path('<int:pk>/edit/', views.lead_edit, name='lead_edit'),
    path('<int:pk>/move/', views.lead_move, name='lead_move'),
    path('<int:pk>/notes/', views.lead_note_create, name='lead_note_create'),
    path('<int:pk>/notes/<int:note_pk>/delete/', views.lead_note_delete, name='lead_note_delete'),
    path('<int:pk>/convert/', views.lead_convert, name='lead_convert'),
    path('<int:pk>/delete/', views.lead_delete, name='lead_delete'),
]
