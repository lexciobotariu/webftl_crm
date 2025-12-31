from django.contrib import admin

from .models import GitHubCommit, GitHubPullRequest


@admin.register(GitHubCommit)
class GitHubCommitAdmin(admin.ModelAdmin):
    list_display = ('sha', 'task', 'author', 'created_at')
    list_filter = ('task__project',)
    search_fields = ('sha', 'message')


@admin.register(GitHubPullRequest)
class GitHubPullRequestAdmin(admin.ModelAdmin):
    list_display = ('number', 'title', 'task', 'status', 'updated_at')
    list_filter = ('status', 'task__project')
