from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.clients.models import visible_clients
from apps.projects.models import ProjectAccess, can_access_project


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
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
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


def _can_open_note_parent(user, note):
    """A client the user can already see, or a project they can already open."""
    if note.client_id:
        return visible_clients(user).filter(pk=note.client_id).exists()
    if note.project_id:
        return can_access_project(user, note.project)
    return False


def _public_view_own_q(user):
    """Public notes on a parent :func:`_can_open_note_parent` would allow.

    Project visibility matches :func:`can_access_project` for a non-admin:
    a ProjectAccess row, ``projects_view_all``, or ``projects_edit_all``.
    """
    visible = Q(client_id__in=visible_clients(user).values('pk'))
    if user.has_app_permission('projects_view_all') or user.has_app_permission('projects_edit_all'):
        visible |= Q(project__isnull=False)
    else:
        visible |= Q(project_id__in=ProjectAccess.objects.filter(user=user).values('project_id'))
    return Q(is_private=False) & visible


def notes_visible_to_user(user, queryset=None):
    """Notes this user may list. Same rules as :func:`can_view_note`.

    A private note is only the author's. ``role=admin`` does not see someone
    else's. A public note needs ``access_notes`` and either a parent the user
    can already open or ``notes_view_all``. Clients or projects access alone
    does not include any note.
    """
    qs = queryset if queryset is not None else Note.objects.all()
    if not user.has_app_permission('access_notes'):
        return qs.none()
    own_private = Q(is_private=True, created_by=user)
    if user.has_app_permission('notes_view_all'):
        return qs.filter(own_private | Q(is_private=False))
    return qs.filter(own_private | _public_view_own_q(user))


def can_view_note(user, note):
    """Whether this user may open this note.

    Privacy is decided before ``has_app_permission``, which is true for every
    key when ``role=admin``. That bypass must not reveal a private note.
    """
    if note.is_private and note.created_by_id != user.id:
        return False
    if not user.has_app_permission('access_notes'):
        return False
    if note.is_private:
        return True
    if user.has_app_permission('notes_view_all'):
        return True
    return _can_open_note_parent(user, note)


def can_create_note(user, project=None, client=None):
    """Create a private or public note on a parent the user can already open.

    ``access_notes`` is required. There is no separate create flag. Opening
    the client or the project is :func:`visible_clients` or
    :func:`can_access_project`, not ``can_work_on_project``.
    """
    if not user.has_app_permission('access_notes'):
        return False
    if client is not None:
        return visible_clients(user).filter(pk=client.pk).exists()
    if project is not None:
        return can_access_project(user, project)
    return False


def can_modify_note(user, note):
    """Edit or delete this note.

    The author can change their own note, private or public, while they can
    still open its parent. ``notes_edit_public`` can change any public note,
    including one they did not write and one whose parent they cannot open.
    It never applies to a private note. Privacy is checked before the admin
    bypass in ``has_app_permission``.
    """
    if note.is_private and note.created_by_id != user.id:
        return False
    if not user.has_app_permission('access_notes'):
        return False
    if note.is_private:
        return _can_open_note_parent(user, note)
    if user.has_app_permission('notes_edit_public'):
        return True
    if note.created_by_id != user.id:
        return False
    return _can_open_note_parent(user, note)
