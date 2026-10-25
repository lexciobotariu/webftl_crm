from django.urls import path

from . import views

urlpatterns = [
    path('tasks/', views.task_events, name='live_task_events'),
]
