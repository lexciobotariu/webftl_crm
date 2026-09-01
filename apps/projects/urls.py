from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path('', views.project_list, name='project_list'),
    path('create/', views.project_create, name='project_create'),
    path('<int:pk>/overview/', views.project_detail, name='project_detail'),
    path('<int:pk>/tasks/', views.project_detail, name='project_detail_tasks'),
    path('<int:pk>/notes/', views.project_detail, name='project_detail_notes'),
    path('<int:pk>/kanban/', views.project_board, name='project_board'),
    path('<int:pk>/edit/', views.project_edit, name='project_edit'),
    path('<int:pk>/delete/', views.project_delete, name='project_delete'),
    path('<int:pk>/settings/', views.project_settings, name='project_settings'),
    path('<int:pk>/settings/update/', views.project_settings_update, name='project_settings_update'),
    path('<int:pk>/statuses/create/', views.status_create, name='status_create'),
    path('<int:pk>/statuses/<int:status_pk>/delete/', views.status_delete, name='status_delete'),
    path('<int:pk>/statuses/<int:status_pk>/toggle-visibility/', views.status_toggle_visibility, name='status_toggle_visibility'),
    path('<int:pk>/statuses/<int:status_pk>/toggle-done/', views.status_toggle_done, name='status_toggle_done'),
    path('<int:pk>/statuses/reorder/', views.reorder_statuses, name='reorder_statuses'),
    path('<int:pk>/labels/create/', views.label_create, name='label_create'),
    path('<int:pk>/labels/<int:label_pk>/delete/', views.label_delete, name='label_delete'),
    # Bare /projects/<pk>/ lands on the overview tab.
    path('<int:pk>/', RedirectView.as_view(pattern_name='project_detail'), name='project_root'),
]
