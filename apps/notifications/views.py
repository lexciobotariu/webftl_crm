from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission

from .models import Notification
from .services import inbox_for, unread_count

# Older read notifications shown under the unread ones.
EARLIER_LIMIT = 50


def _inbox_context(user):
    notes = inbox_for(user)
    return {
        'unread': list(notes.filter(read_at__isnull=True)),
        'earlier': list(notes.filter(read_at__isnull=False)[:EARLIER_LIMIT]),
    }


def _changed(response):
    response['HX-Trigger'] = 'notificationsChanged'
    return response


@login_required
@require_permission('access_tasks')
def inbox(request):
    return render(request, 'notifications/inbox.html', _inbox_context(request.user))


@login_required
@require_permission('access_tasks')
def inbox_count(request):
    """The sidebar badge's number, fetched when the tab becomes visible again."""
    return HttpResponse(str(unread_count(request.user)), content_type='text/plain')


@login_required
@require_permission('access_tasks')
@require_POST
def notification_read(request, pk):
    note = get_object_or_404(inbox_for(request.user), pk=pk)
    if note.read_at is None:
        note.read_at = timezone.now()
        note.save(update_fields=['read_at'])
    return _changed(render(request, 'notifications/partials/item.html', {'note': note}))


@login_required
@require_permission('access_tasks')
@require_POST
def notification_read_all(request):
    Notification.objects.filter(recipient=request.user, read_at__isnull=True).update(read_at=timezone.now())
    return _changed(render(request, 'notifications/partials/list.html', _inbox_context(request.user)))
