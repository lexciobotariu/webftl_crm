from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='portal_home'),
    path('sign-in/', views.login, name='portal_login'),
    path('sign-in/<str:token>/', views.link, name='portal_link'),
    path('sign-out/', views.logout, name='portal_logout'),
    path('messages/', views.messages, name='portal_messages'),
    path('estimates/<int:pk>/', views.estimate_detail, name='portal_estimate'),
    path('estimates/<int:pk>/pdf/', views.estimate_pdf_view, name='portal_estimate_pdf'),
    path('invoices/<int:pk>/pdf/', views.invoice_pdf_view, name='portal_invoice_pdf'),
]
