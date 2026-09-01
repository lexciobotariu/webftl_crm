from django.contrib import admin

from .models import Note


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ['title', 'get_parent', 'is_private', 'created_by', 'updated_at']
    list_filter = ['is_private', 'created_at', 'updated_at']
    search_fields = ['title', 'description']
    readonly_fields = ['created_at', 'updated_at']

    def get_parent(self, obj):
        return obj.client or obj.project
    get_parent.short_description = 'Parent'
