from django.urls import path

from . import views

urlpatterns = [
    path('', views.plan_list, name='maintenance_plan_list'),
    path('new/', views.plan_create, name='maintenance_plan_create'),
    path('<int:pk>/', views.plan_detail, name='maintenance_plan_detail'),
    path('<int:pk>/edit/', views.plan_edit, name='maintenance_plan_edit'),
    path('<int:pk>/status/', views.plan_status, name='maintenance_plan_status'),
    path('<int:pk>/checks/', views.check_create, name='maintenance_check_create'),
    path('<int:pk>/checks/run/', views.check_run, name='maintenance_check_run'),
    path('<int:pk>/checks/<int:check_pk>/delete/', views.check_delete, name='maintenance_check_delete'),
    path('<int:pk>/invoicing/', views.plan_invoicing, name='maintenance_plan_invoicing'),
    path('<int:pk>/extra-hours/', views.plan_extra_hours, name='maintenance_plan_extra_hours'),
    path('<int:pk>/reports/<int:year>-<int:month>/', views.report_detail, name='maintenance_report'),
    path('<int:pk>/reports/<int:year>-<int:month>/pdf/', views.report_pdf, name='maintenance_report_pdf'),
    path('<int:pk>/reports/<int:year>-<int:month>/email/', views.report_email, name='maintenance_report_email'),
    path('sites/new/', views.site_create, name='maintenance_site_create'),
    path('sites/<int:pk>/', views.site_detail, name='maintenance_site_detail'),
    path('sites/<int:pk>/edit/', views.site_edit, name='maintenance_site_edit'),
    path('sites/<int:pk>/delete/', views.site_delete, name='maintenance_site_delete'),
    path('sites/<int:pk>/logins/', views.credentials_list, name='maintenance_credentials'),
    path('sites/<int:pk>/logins/new/', views.credential_create, name='maintenance_credential_create'),
    path('sites/<int:pk>/logins/<int:credential_pk>/edit/', views.credential_edit, name='maintenance_credential_edit'),
    path('sites/<int:pk>/logins/<int:credential_pk>/delete/', views.credential_delete,
         name='maintenance_credential_delete'),
    path('sites/<int:pk>/logins/<int:credential_pk>/show/', views.credential_reveal,
         name='maintenance_credential_reveal'),
]
