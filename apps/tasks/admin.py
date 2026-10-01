from django.contrib import admin

from .models import Label, Subtask, Task, TimeEntry


class SubtaskInline(admin.TabularInline):
    model = Subtask
    extra = 0


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'number', 'project', 'status', 'assignee', 'priority', 'due_date')
    list_filter = ('project', 'status', 'priority', 'assignee')
    search_fields = ('title', 'description')
    readonly_fields = ('number',)

    def get_readonly_fields(self, request, obj=None):
        # The number belongs to the project's sequence, so a task cannot move.
        if obj is not None:
            return ('number', 'project')
        return self.readonly_fields
    inlines = [SubtaskInline]


@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'color')
    list_filter = ('project',)


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ('task', 'user', 'started_at', 'ended_at')
    list_filter = ('user',)
    search_fields = ('task__title', 'note', 'user__email')
