from django.urls import path

from . import views

urlpatterns = [
    path('', views.settings_page, name='settings'),
    path('currencies/', views.currency_add, name='currency_add'),
    path('currencies/<int:pk>/delete/', views.currency_delete, name='currency_delete'),
    path('bank-accounts/new/', views.bank_account_add, name='bank_account_add'),
    path('bank-accounts/<int:pk>/', views.bank_account_edit, name='bank_account_edit'),
    path('bank-accounts/<int:pk>/archive/', views.bank_account_archive, name='bank_account_archive'),
    path('bank-accounts/<int:pk>/delete/', views.bank_account_delete, name='bank_account_delete'),
]
