from django.contrib import admin

from .models import Task, Subtask, Comment, Attachment, Label


class SubtaskInline(admin.TabularInline):
    model = Subtask
    extra = 0


class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0
    readonly_fields = ['author', 'created_at']


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'status', 'assignee', 'priority', 'due_date')
    list_filter = ('project', 'status', 'priority', 'assignee')
    search_fields = ('title', 'description')
    inlines = [SubtaskInline, CommentInline]


@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'color')
    list_filter = ('project',)
