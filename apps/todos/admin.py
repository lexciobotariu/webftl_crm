from django.contrib import admin

from .models import Todo


@admin.register(Todo)
class TodoAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'client', 'due_date', 'is_completed', 'created_at')
    list_filter = ('is_completed', 'due_date', 'client', 'owner')
    search_fields = ('title', 'description')
    date_hierarchy = 'created_at'
    ordering = ['is_completed', 'due_date', '-created_at']
    raw_id_fields = ('owner', 'client')
