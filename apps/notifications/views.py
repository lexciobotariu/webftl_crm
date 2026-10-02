import json
from datetime import timedelta
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST
from django_htmx.http import replace_url

from apps.accounts.decorators import require_permission
from apps.tasks.views import render_task_drawer

from .models import Notification
from .services import inbox_for, unread_count

TABS = [('all', 'All'), ('unread', 'Unread'), ('mentions', 'Mentions')]
SHOWS = tuple(value for value, _ in TABS)
PAGE_SIZE = 50
MAX_LIMIT = 1000


def _limit(raw):
    """The number of rows asked for, in whole pages and never past MAX_LIMIT."""
    try:
        wanted = int(raw)
    except (TypeError, ValueError):
        return PAGE_SIZE
    wanted = min(max(wanted, PAGE_SIZE), MAX_LIMIT)
    return -(-wanted // PAGE_SIZE) * PAGE_SIZE


def group_by_day(notes, today):
    """``notes`` (newest first) in Today / Yesterday / This week / Older groups.

    ``today`` is a local date. This week starts on Monday and covers what is
    not already Today or Yesterday; empty groups are left out.
    """
    week_start = today - timedelta(days=today.weekday())
    yesterday = today - timedelta(days=1)
    groups = [
        {'key': 'today', 'label': 'Today', 'rows': []},
        {'key': 'yesterday', 'label': 'Yesterday', 'rows': []},
        {'key': 'week', 'label': 'This week', 'rows': []},
        {'key': 'older', 'label': 'Older', 'rows': []},
    ]
    for note in notes:
        day = timezone.localtime(note.created_at).date()
        if day >= today:
            index = 0
        elif day == yesterday:
            index = 1
        elif day >= week_start:
            index = 2
        else:
            index = 3
        groups[index]['rows'].append(note)
    for group in groups:
        group['count'] = len(group['rows'])
    return [group for group in groups if group['rows']]


def _mark_unread_possible(user, notes):
    """Set ``can_mark_unread``: false for a read note when an unread one of its kind already exists.

    There is at most one unread row per task and kind, so marking a second one
    unread would have nowhere to go.
    """
    notes = list(notes)
    taken = set(
        Notification.objects.filter(
            recipient=user, read_at__isnull=True, task_id__in={note.task_id for note in notes}
        ).values_list('task_id', 'kind')
    )
    for note in notes:
        note.can_mark_unread = (note.task_id, note.kind) not in taken
    return notes


def _filtered(user, show, keep=None):
    """The notifications of a tab. ``keep`` is the one open in the pane.

    Opening a notification marks it read, so on the Unread tab it would drop out of
    the list at the next refresh while the pane still shows it, and the pane's
    controls would have no row to act on. It stays for as long as it is open.
    """
    notes = inbox_for(user).select_related('task__status')
    if show == 'unread':
        unread = Q(read_at__isnull=True)
        return notes.filter(unread | Q(pk=keep)) if keep else notes.filter(unread)
    if show == 'mentions':
        return notes.filter(kind=Notification.MENTIONED)
    return notes


def _show(raw):
    return raw if raw in SHOWS else 'all'


def _page_url(show, pk=None):
    """The Inbox address for a tab and, optionally, the notification open in the pane."""
    params = {'show': show}
    if pk is not None:
        params['n'] = pk
    return f"{reverse('inbox')}?{urlencode(params)}"


def _pk(raw):
    """A notification id from the address, or None; ``str.isdigit`` alone accepts "²"."""
    raw = raw or ''
    return int(raw) if raw.isascii() and raw.isdigit() else None


def _list_context(user, show='all', limit=PAGE_SIZE, keep=None):
    show = _show(show)
    notes = _filtered(user, show, keep)
    total = notes.count()
    rows = _mark_unread_possible(user, notes[:limit])
    more_url = None
    # At MAX_LIMIT there is no next page to ask for: the button would do nothing.
    if total > limit and limit < MAX_LIMIT:
        more_url = '?' + urlencode({'show': show, 'limit': limit + PAGE_SIZE})
    return {
        'tabs': TABS,
        'show': show,
        'groups': group_by_day(rows, timezone.localdate()),
        'total': total,
        'limit': limit,
        'more_url': more_url,
        'refresh_url': '?' + urlencode({'show': show, 'limit': limit}),
        'unread_total': unread_count(user),
    }


def _pane_context(request, note, show):
    """The right pane for ``note``: what happened, then the task itself (embedded drawer)."""
    task = render_task_drawer(request, note.task_id, embedded=True)
    return {
        'note': note,
        'show': show,
        'task_html': mark_safe(task.content.decode()) if task.status_code == 200 else '',
    }


def _changed(response, **events):
    response['HX-Trigger'] = json.dumps({'notificationsChanged': True, **events})
    return response


def _chip(user):
    """The Unread tab's count, as an out-of-band swap."""
    return render_to_string('notifications/partials/unread_chip.html', {'unread_total': unread_count(user), 'oob': True})


def _row_html(request, note, show):
    """The list row for ``note`` as an out-of-band swap, so any response can refresh it."""
    _mark_unread_possible(request.user, [note])
    return render_to_string(
        'notifications/partials/item.html',
        {'note': note, 'oob': True, 'show': show, 'selected_pk': note.pk},
        request=request,
    )


def _oob_only(request, note):
    """Row and Unread count; the request itself swaps nothing."""
    row = _row_html(request, note, _show(request.GET.get('show')))
    return _changed(HttpResponse(row + _chip(request.user)))


@login_required
@require_permission('access_tasks')
def inbox(request):
    open_pk = _pk(request.GET.get('n'))
    context = _list_context(
        request.user, request.GET.get('show'), _limit(request.GET.get('limit')), keep=open_pk
    )
    selected = None
    # A list refresh only names the open notification so it is kept; it swaps the
    # list alone, so the pane (the whole task) is not rendered for it.
    if open_pk is not None and request.GET.get('list') != '1':
        # A link or a reload names a notification: show it, but a GET changes
        # nothing; the pane marks it read with its own POST once it loads.
        selected = inbox_for(request.user).select_related('task__status').filter(pk=open_pk).first()
    if selected is not None:
        context.update(_pane_context(request, selected, context['show']))
        context['selected_pk'] = selected.pk
    return render(request, 'notifications/inbox.html', context)


@login_required
@require_permission('access_tasks')
def inbox_count(request):
    """The sidebar badge's number, fetched when the tab becomes visible again."""
    return HttpResponse(str(unread_count(request.user)), content_type='text/plain')


@login_required
@require_permission('access_tasks')
@require_POST
def notification_open(request, pk):
    """Open the notification in the right pane and mark it read, in one request.

    The address follows (replaced, not pushed, so moving with J/K does not fill
    the history) and the row and the Unread count update out of band.
    """
    note = get_object_or_404(inbox_for(request.user).select_related('task__status'), pk=pk)
    show = _show(request.GET.get('show'))
    if note.read_at is None:
        note.read_at = timezone.now()
        note.save(update_fields=['read_at'])
    response = render(request, 'notifications/partials/pane.html', _pane_context(request, note, show))
    response.content += (_row_html(request, note, show) + _chip(request.user)).encode()
    replace_url(response, _page_url(show, note.pk))
    return _changed(response)


@login_required
@require_permission('access_tasks')
@require_POST
def notification_read(request, pk):
    note = get_object_or_404(inbox_for(request.user), pk=pk)
    if note.read_at is None:
        note.read_at = timezone.now()
        note.save(update_fields=['read_at'])
    return _oob_only(request, note)


@login_required
@require_permission('access_tasks')
@require_POST
def notification_unread(request, pk):
    note = get_object_or_404(inbox_for(request.user), pk=pk)
    if note.read_at is not None:
        try:
            with transaction.atomic():
                note.read_at = None
                note.save(update_fields=['read_at'])
        except IntegrityError:
            # An unread one of this kind exists already; this one stays read.
            note.refresh_from_db()
    return _oob_only(request, note)


@login_required
@require_permission('access_tasks')
@require_POST
def notification_delete(request, pk):
    """Delete it; the browser picks what opens next, from the list it shows."""
    note = get_object_or_404(inbox_for(request.user), pk=pk)
    note_id = note.pk
    note.delete()
    gone = f'<div id="notification-{note_id}" hx-swap-oob="delete"></div>'
    return _changed(HttpResponse(gone + _chip(request.user)), notificationDeleted={'id': note_id})


@login_required
@require_permission('access_tasks')
@require_POST
def notification_read_all(request):
    """Every unread notification of the person, whatever the tab or page shows."""
    Notification.objects.filter(recipient=request.user, read_at__isnull=True).update(read_at=timezone.now())
    limit = _limit(request.POST.get('limit') or request.GET.get('limit'))
    context = _list_context(request.user, request.GET.get('show'), limit, keep=_pk(request.POST.get('n')))
    return _changed(render(request, 'notifications/partials/list.html', {**context, 'oob_chip': True}))
