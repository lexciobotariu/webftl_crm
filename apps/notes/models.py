from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.projects.models import can_access_project


class Note(models.Model):
    """
    Notes attached to clients or projects.
    Supports private (creator-only) and public (shared with team) visibility.
    """
    # Polymorphic relationship - exactly one must be set
    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='note_objects'
    )
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='note_objects'
    )

    # Content fields
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    # Privacy
    is_private = models.BooleanField(default=False)

    # Ownership & tracking
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notes_created'
    )
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notes_modified'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']  # Most recently modified first

    def __str__(self):
        parent = self.client or self.project
        return f"{self.title} ({parent})"

    def clean(self):
        """Ensure exactly one parent is set"""
        if not (bool(self.client) ^ bool(self.project)):
            raise ValidationError("Note must belong to either a client or project")


def can_view_note(user, note):
    """Check if user can view this note"""
    if user.is_admin:
        return True

    # Private notes: only creator
    if note.is_private:
        return note.created_by == user

    # Public client notes: admin-only (already handled above)
    if note.client:
        return False

    # Public project notes: any project member
    if note.project:
        return can_access_project(user, note.project, 'viewer')

    return False


def can_create_note(user, project=None, client=None):
    """Check if user can create notes"""
    if user.is_admin:
        return True

    if client:
        return False  # Only admins can create client notes

    if project:
        return can_access_project(user, project, 'editor')

    return False


def can_modify_note(user, note):
    """Check if user can edit/delete this note"""
    if user.is_admin:
        return True

    # Only creator can modify their own notes
    return note.created_by == user
