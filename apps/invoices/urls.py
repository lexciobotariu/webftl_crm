from django.urls import path

from . import views

urlpatterns = [
    path('', views.invoice_list, name='invoice_list'),
    path('create/', views.invoice_create, name='invoice_create'),
    path('<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('<int:pk>/edit/', views.invoice_edit, name='invoice_edit'),
    path('<int:pk>/send/', views.invoice_mark_sent, name='invoice_mark_sent'),
    path('<int:pk>/cancel/', views.invoice_cancel, name='invoice_cancel'),
    path('<int:pk>/delete/', views.invoice_delete, name='invoice_delete'),
    path('<int:pk>/print/', views.invoice_print, name='invoice_print'),
    path('<int:pk>/repeat/', views.invoice_recurring, name='invoice_recurring'),
    path('<int:pk>/repeat/stop/', views.invoice_recurring_stop, name='invoice_recurring_stop'),
    path('<int:pk>/pdf/', views.invoice_pdf_download, name='invoice_pdf'),
    path('<int:pk>/email/<str:kind>/', views.invoice_email, name='invoice_email'),
    path('<int:pk>/lines/create/', views.line_create, name='invoice_line_create'),
    path('<int:pk>/lines/<int:line_pk>/edit/', views.line_edit, name='invoice_line_edit'),
    path('<int:pk>/lines/<int:line_pk>/delete/', views.line_delete, name='invoice_line_delete'),
    path('<int:pk>/payments/create/', views.payment_create, name='invoice_payment_create'),
    path('<int:pk>/payments/<int:payment_pk>/delete/', views.payment_delete, name='invoice_payment_delete'),
]
