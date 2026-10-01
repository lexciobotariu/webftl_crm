"""Creating and reading notifications. See :class:`~.models.Notification`."""
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User
from apps.tasks.models import TaskActivity, visible_tasks

from .models import Notification


def people_who_can_see(task):
    """Active people who can open ``task`` and have the Tasks module.

    The query form of ``can_view_task`` plus ``access_tasks``: admins,
    ``tasks_view_all``, or ``access_tasks`` with a ProjectAccess row.
    """
    return (
        User.objects.filter(is_active=True)
        .filter(
            Q(role='admin')
            | Q(permission_preset__access_tasks=True, permission_preset__tasks_view_all=True)
            | Q(permission_preset__access_tasks=True, project_access__project_id=task.project_id)
        )
        .distinct()
        .order_by('name')
    )


def notify(recipient, actor, task, kind, activity=None):
    """Tell ``recipient``; never the person who did it."""
    if recipient is None or actor is None or recipient.pk == actor.pk:
        return
    fields = {'actor': actor, 'activity': activity, 'created_at': timezone.now()}
    unread = Notification.objects.filter(recipient=recipient, task=task, kind=kind, read_at__isnull=True)
    if unread.update(**fields):
        return
    try:
        with transaction.atomic():
            Notification.objects.create(recipient=recipient, task=task, kind=kind, **fields)
    except IntegrityError:
        # Someone else created the unread row in between; move it up instead.
        unread.update(**fields)


def notify_assigned(task, actor):
    notify(task.assignee, actor, task, Notification.ASSIGNED)


def withdraw_assigned(task, previous_assignee):
    """The task moved on to someone else: an unread "assigned you" is no longer true."""
    if previous_assignee is not None:
        Notification.objects.filter(
            recipient=previous_assignee, task=task, kind=Notification.ASSIGNED, read_at__isnull=True
        ).delete()


def comment_deleted(comment):
    """Before ``comment`` is deleted: keep unread notices that earlier comments still justify.

    An unread row moves to the latest comment, so deleting that comment would
    take the notice for the earlier ones with it. Each row pointing here moves
    back to the newest remaining comment that would have raised it (not by the
    recipient, newer than the recipient's last read notice of that kind, and
    for a mention still naming them). A row with nothing left goes with the
    comment.
    """
    notes = Notification.objects.filter(activity=comment, read_at__isnull=True).select_related('recipient')
    for note in notes:
        candidates = (
            TaskActivity.objects.filter(task_id=comment.task_id, activity_type='comment')
            .exclude(pk=comment.pk)
            .exclude(user_id=note.recipient_id)
            .order_by('-created_at', '-pk')
        )
        last_read = (
            Notification.objects.filter(
                recipient_id=note.recipient_id, task_id=comment.task_id, kind=note.kind, read_at__isnull=False
            )
            .order_by('-created_at')
            .values_list('created_at', flat=True)
            .first()
        )
        if last_read is not None:
            candidates = candidates.filter(created_at__gt=last_read)
        if note.kind == Notification.MENTIONED:
            candidates = candidates.filter(content__contains=f'@{note.recipient.name}')
        previous = candidates.first()
        if previous is not None:
            Notification.objects.filter(pk=note.pk).update(
                activity=previous, actor_id=previous.user_id, created_at=previous.created_at
            )


def _mentioned(task, content, mention_ids):
    """The people picked in the @ menu who can see the task and are still named in the text."""
    ids = set()
    for value in mention_ids or ():
        try:
            ids.add(int(value))
        except (TypeError, ValueError):
            continue
    if not ids:
        return []
    return [person for person in people_who_can_see(task).filter(pk__in=ids) if f'@{person.name}' in content]


def notify_comment(comment, mention_ids=()):
    """"Mentioned" for the people named, "commented" for everyone else who follows the task.

    Followers are the assignee, the creator and earlier commenters, read in one
    query from the activity log.
    """
    task, actor = comment.task, comment.user
    mentioned = _mentioned(task, comment.content, mention_ids)
    for person in mentioned:
        notify(person, actor, task, Notification.MENTIONED, comment)

    follower_ids = set(
        TaskActivity.objects.filter(task=task, activity_type__in=['created', 'comment'], user__isnull=False)
        .values_list('user_id', flat=True)
    )
    if task.assignee_id:
        follower_ids.add(task.assignee_id)
    follower_ids -= {person.pk for person in mentioned}
    follower_ids.discard(actor.pk if actor else None)
    for person in User.objects.filter(pk__in=follower_ids, is_active=True):
        notify(person, actor, task, Notification.COMMENTED, comment)


def inbox_for(user):
    """``user``'s notifications on tasks they can still see, unread first."""
    return (
        Notification.objects.filter(recipient=user, task__in=visible_tasks(user).values('pk'))
        .select_related('actor', 'task__project', 'activity')
    )


def unread_count(user):
    return inbox_for(user).filter(read_at__isnull=True).count()
