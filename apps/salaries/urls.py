from django.urls import path

from . import views

urlpatterns = [
    # Salary list and create
    path('', views.salary_list, name='salary_list'),
    path('create/', views.salary_create, name='salary_create'),

    # Salary detail, edit, delete
    path('<int:pk>/', views.salary_detail, name='salary_detail'),
    path('<int:pk>/edit/', views.salary_edit, name='salary_edit'),
    path('<int:pk>/delete/', views.salary_delete, name='salary_delete'),

    # Month CRUD
    path('<int:pk>/months/create/', views.month_create, name='month_create'),
    path('<int:pk>/months/<int:month_pk>/edit/', views.month_edit, name='month_edit'),
    path('<int:pk>/months/<int:month_pk>/delete/', views.month_delete, name='month_delete'),

    # Payment CRUD
    path('<int:pk>/payments/create/', views.payment_create, name='payment_create'),
    path('<int:pk>/payments/<int:payment_pk>/edit/', views.payment_edit, name='payment_edit'),
    path('<int:pk>/payments/<int:payment_pk>/delete/', views.payment_delete, name='payment_delete'),
]
