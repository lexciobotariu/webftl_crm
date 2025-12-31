from django.contrib import admin

from .models import Project, Status


class StatusInline(admin.TabularInline):
    model = Status
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'client', 'github_sync_enabled', 'created_at')
    list_filter = ('client', 'github_sync_enabled')
    search_fields = ('name', 'client__name')
    inlines = [StatusInline]


@admin.register(Status)
class StatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'order')
    list_filter = ('project',)
