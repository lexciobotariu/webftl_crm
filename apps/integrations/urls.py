from django.urls import path

from . import views

urlpatterns = [
    path('github/webhook/', views.github_webhook, name='github_webhook'),
    path('github/sync/<int:project_pk>/', views.github_sync, name='github_sync'),
]
