from django.urls import path

from apps.leads import settings_views as lead_settings

from . import views

urlpatterns = [
    path('', views.settings_page, name='settings'),
    path('appearance/', views.settings_appearance, name='settings_appearance'),
    path('bank-accounts/', views.settings_bank_accounts, name='settings_bank_accounts'),
    path('bank-accounts/new/', views.bank_account_add, name='bank_account_add'),
    path('bank-accounts/<int:pk>/', views.bank_account_edit, name='bank_account_edit'),
    path('bank-accounts/<int:pk>/archive/', views.bank_account_archive, name='bank_account_archive'),
    path('bank-accounts/<int:pk>/delete/', views.bank_account_delete, name='bank_account_delete'),
    path('currencies/', views.settings_currencies, name='settings_currencies'),
    path('currencies/add/', views.currency_add, name='currency_add'),
    path('currencies/<int:pk>/delete/', views.currency_delete, name='currency_delete'),
    path('lead-statuses/', lead_settings.settings_lead_statuses, name='settings_lead_statuses'),
    path('lead-statuses/add/', lead_settings.lead_status_add, name='lead_status_add'),
    path('lead-statuses/<int:pk>/', lead_settings.lead_status_edit, name='lead_status_edit'),
    path('lead-statuses/<int:pk>/delete/', lead_settings.lead_status_delete, name='lead_status_delete'),
    path('lead-sources/', lead_settings.settings_lead_sources, name='settings_lead_sources'),
    path('lead-sources/add/', lead_settings.lead_source_add, name='lead_source_add'),
    path('lead-sources/<int:pk>/', lead_settings.lead_source_edit, name='lead_source_edit'),
    path('lead-sources/<int:pk>/delete/', lead_settings.lead_source_delete, name='lead_source_delete'),
    path('storage/', views.settings_storage, name='settings_storage'),
]
