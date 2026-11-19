from django.urls import path

from . import views

urlpatterns = [
    path('', views.service_list, name='service_list'),
    path('new/', views.service_create, name='service_create'),
    path('<int:pk>/', views.service_detail, name='service_detail'),
    path('<int:pk>/sections/', views.service_sections, name='service_sections'),
    path('<int:pk>/edit/', views.service_edit, name='service_edit'),
    path('<int:pk>/status/', views.service_status, name='service_status'),
    path('<int:pk>/invoicing/', views.service_invoicing, name='service_invoicing'),
    path('<int:pk>/extra-hours/', views.service_extra_hours, name='service_extra_hours'),
    path('<int:pk>/reports/<int:year>-<int:month>/', views.report_detail, name='service_report'),
    path('<int:pk>/reports/<int:year>-<int:month>/pdf/', views.report_pdf, name='service_report_pdf'),
    path('<int:pk>/reports/<int:year>-<int:month>/email/', views.report_email, name='service_report_email'),
    path('sites/new/', views.site_create, name='site_create'),
    path('sites/<int:pk>/', views.site_detail, name='site_detail'),
    path('sites/<int:pk>/edit/', views.site_edit, name='site_edit'),
    path('sites/<int:pk>/delete/', views.site_delete, name='site_delete'),
    path('sites/<int:pk>/logins/', views.credentials_list, name='site_credentials'),
    path('sites/<int:pk>/logins/new/', views.credential_create, name='site_credential_create'),
    path('sites/<int:pk>/logins/<int:credential_pk>/edit/', views.credential_edit, name='site_credential_edit'),
    path('sites/<int:pk>/logins/<int:credential_pk>/delete/', views.credential_delete,
         name='site_credential_delete'),
    path('sites/<int:pk>/logins/<int:credential_pk>/show/', views.credential_reveal,
         name='site_credential_reveal'),
]
