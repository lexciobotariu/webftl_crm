from django.urls import path

from . import estimate_views as views

urlpatterns = [
    path('', views.estimate_list, name='estimate_list'),
    path('create/', views.estimate_create, name='estimate_create'),
    path('<int:pk>/', views.estimate_detail, name='estimate_detail'),
    path('<int:pk>/edit/', views.estimate_edit, name='estimate_edit'),
    path('<int:pk>/delete/', views.estimate_delete, name='estimate_delete'),
    path('<int:pk>/send/', views.estimate_mark_sent, name='estimate_mark_sent'),
    path('<int:pk>/email/', views.estimate_email, name='estimate_email'),
    path('<int:pk>/answer/<str:answer>/', views.estimate_answer, name='estimate_answer'),
    path('<int:pk>/convert/', views.estimate_convert, name='estimate_convert'),
    path('<int:pk>/print/', views.estimate_print, name='estimate_print'),
    path('<int:pk>/pdf/', views.estimate_pdf_download, name='estimate_pdf'),
    path('<int:pk>/lines/create/', views.estimate_line_create, name='estimate_line_create'),
    path('<int:pk>/lines/<int:line_pk>/edit/', views.estimate_line_edit, name='estimate_line_edit'),
    path('<int:pk>/lines/<int:line_pk>/delete/', views.estimate_line_delete, name='estimate_line_delete'),
]
