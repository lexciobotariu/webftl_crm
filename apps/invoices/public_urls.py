from django.urls import path

from . import public_views as views

urlpatterns = [
    path('<int:pk>/<str:token>/', views.estimate_public, name='estimate_public'),
    path('<int:pk>/<str:token>/pdf/', views.estimate_public_pdf, name='estimate_public_pdf'),
]
