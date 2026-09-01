from django.contrib import admin

from .models import Label, Subtask, Task


class SubtaskInline(admin.TabularInline):
    model = Subtask
    extra = 0


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'status', 'assignee', 'priority', 'due_date')
    list_filter = ('project', 'status', 'priority', 'assignee')
    search_fields = ('title', 'description')
    inlines = [SubtaskInline]


@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'color')
    list_filter = ('project',)
