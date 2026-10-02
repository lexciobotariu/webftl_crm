from django.urls import path

from . import views

urlpatterns = [
    path('', views.inbox, name='inbox'),
    path('count/', views.inbox_count, name='inbox_count'),
    path('read-all/', views.notification_read_all, name='notification_read_all'),
    path('<int:pk>/open/', views.notification_open, name='notification_open'),
    path('<int:pk>/read/', views.notification_read, name='notification_read'),
    path('<int:pk>/unread/', views.notification_unread, name='notification_unread'),
    path('<int:pk>/delete/', views.notification_delete, name='notification_delete'),
]
