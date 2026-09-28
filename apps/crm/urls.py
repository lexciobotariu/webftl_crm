from django.urls import path

from . import views

urlpatterns = [
    path('', views.settings_page, name='settings'),
    path('currencies/', views.currency_add, name='currency_add'),
    path('currencies/<int:pk>/delete/', views.currency_delete, name='currency_delete'),
]
