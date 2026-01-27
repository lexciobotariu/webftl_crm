from django.urls import path

from . import views

urlpatterns = [
    path('', views.salary_list, name='salary_list'),
    path('create/', views.salary_create, name='salary_create'),
    path('<int:pk>/', views.salary_detail, name='salary_detail'),
]
