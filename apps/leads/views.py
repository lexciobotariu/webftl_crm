"""Leads: a list and a board, one page per lead, notes, and "Convert to client".

Everything needs the Leads module (``access_leads``); everyone with it sees
every lead. Estimates for a lead also need the invoices permissions, and
converting needs ``clients_create``. Deleting a lead is for admins.
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.clients.models import ClientMessage

from . import services
from .forms import ConvertForm, LeadForm, LeadNoteForm
from .models import LeadNote, LeadSource, LeadStatus

LEADS_PER_PAGE = 25
# Won and Lost columns of the board show the last month only; the list has them all.
CLOSED_ON_BOARD = timedelta(days=30)
VIEWS = ('board', 'list')


def _redirect(url):
    response = HttpResponse('')
    response['HX-Redirect'] = url
    return response


def _lead_or_404(user, pk):
    return get_object_or_404(services.visible_leads(user), pk=pk)


def _filtered(request, leads):
    """The toolbar filters: text, source, assignee ('me', 'none' or an id), follow-up due."""
    query = request.GET.get('q', '').strip()[:100]
    if query:
        leads = leads.filter(
            Q(name__icontains=query) | Q(contact_name__icontains=query) | Q(email__icontains=query)
        )
    source = request.GET.get('source', '')
    if source.isdigit():
        leads = leads.filter(source_id=source)
    assignee = request.GET.get('assignee', '')
    if assignee == 'me':
        leads = leads.filter(assignee=request.user)
    elif assignee == 'none':
        leads = leads.filter(assignee__isnull=True)
    elif assignee.isdigit():
        leads = leads.filter(assignee_id=assignee)
    if request.GET.get('follow_up') == 'due':
        leads = leads.filter(next_follow_up__lte=timezone.localdate(), client__isnull=True)
    return leads, query


def _totals(leads):
    """Estimated value per currency, never added across currencies. Each has ``currency`` and ``amount``."""
    sums = defaultdict(Decimal)
    shapes = {}
    for lead in leads:
        if lead.value is None or lead.currency is None:
            continue
        sums[lead.currency.code] += lead.value
        shapes[lead.currency.code] = lead.currency
    return [SimpleNamespace(code=code, currency=shapes[code], amount=amount) for code, amount in sorted(sums.items())]


@login_required
@require_permission('access_leads')
def lead_list(request):
    """The board (default) or the list, with the same filters. ``?view=list`` picks the list."""
    view = request.GET.get('view', 'board')
    if view not in VIEWS:
        view = 'board'
    leads, query = _filtered(request, services.visible_leads(request.user))
    statuses = list(LeadStatus.objects.all())
    context = {
        'view': view,
        'query': query,
        'statuses': statuses,
        'sources': LeadSource.objects.all(),
        'assignee': request.GET.get('assignee', ''),
        'source': request.GET.get('source', ''),
        'follow_up': request.GET.get('follow_up', ''),
        'today': timezone.localdate(),
        'can_estimate': request.user.has_app_permission('access_invoices')
        and request.user.has_app_permission('invoices_create'),
    }
    if view == 'board':
        since = timezone.now() - CLOSED_ON_BOARD
        on_board = leads.filter(Q(status__kind=LeadStatus.OPEN) | Q(updated_at__gte=since)).order_by(
            'next_follow_up', '-created_at',
        )
        by_status = defaultdict(list)
        for lead in on_board:
            by_status[lead.status_id].append(lead)
        context['columns'] = [
            {'status': status, 'leads': by_status[status.pk], 'totals': _totals(by_status[status.pk])}
            for status in statuses
        ]
    else:
        status = request.GET.get('status', 'open')
        if status == 'open':
            leads = leads.filter(status__kind=LeadStatus.OPEN)
        elif status.isdigit():
            leads = leads.filter(status_id=status)
        else:
            status = 'all'
        leads = leads.order_by('-created_at', '-pk')
        page_obj = Paginator(leads, LEADS_PER_PAGE).get_page(request.GET.get('page', 1))
        context.update(
            leads=page_obj, page_obj=page_obj, total_count=page_obj.paginator.count, status=status,
            totals=_totals(leads),
        )
    return render(request, 'leads/lead_list.html', context)


@login_required
@require_permission('access_leads')
def lead_create(request):
    if request.method == 'POST':
        form = LeadForm(request.POST)
        if form.is_valid():
            lead = form.save(commit=False)
            lead.created_by = request.user
            lead.save()
            return _redirect(reverse('lead_detail', args=[lead.pk]))
    else:
        initial = {'assignee': request.user.pk}
        raw_status = request.GET.get('status', '')
        if raw_status.isdigit():
            initial['status'] = raw_status
        form = LeadForm(initial=initial)
    return render(request, 'leads/partials/lead_drawer.html', {'form': form, 'lead': None})


@login_required
@require_permission('access_leads')
def lead_edit(request, pk):
    lead = _lead_or_404(request.user, pk)
    if request.method == 'POST':
        form = LeadForm(request.POST, instance=lead)
        if form.is_valid():
            form.save()
            return _redirect(reverse('lead_detail', args=[lead.pk]))
    else:
        form = LeadForm(instance=lead)
    return render(request, 'leads/partials/lead_drawer.html', {'form': form, 'lead': lead})


@login_required
@require_permission('access_leads')
def lead_detail(request, pk):
    lead = _lead_or_404(request.user, pk)
    user = request.user
    can_see_estimates = user.has_app_permission('access_invoices')
    estimates = []
    if can_see_estimates:
        from apps.invoices.models import visible_estimates

        estimates = visible_estimates(user).filter(lead=lead).order_by('-number')
    messages = ClientMessage.objects.filter(lead=lead).select_related('author', 'estimate')
    if not can_see_estimates:
        messages = messages.filter(estimate__isnull=True)
    return render(request, 'leads/lead_detail.html', {
        'lead': lead,
        'statuses': LeadStatus.objects.all(),
        'estimates': estimates,
        'can_see_estimates': can_see_estimates,
        'can_estimate': can_see_estimates and user.has_app_permission('invoices_create') and not lead.is_converted,
        'can_convert': user.has_app_permission('clients_create') and not lead.is_converted,
        'notes': lead.lead_notes.select_related('author'),
        'note_form': LeadNoteForm(),
        'sent_messages': messages,
    })


@login_required
@require_permission('access_leads')
@require_POST
def lead_move(request, pk):
    """The board's drag and drop, and the status picker on the lead's page."""
    lead = _lead_or_404(request.user, pk)
    raw = request.POST.get('status', '')
    status = LeadStatus.objects.filter(pk=raw).first() if raw.isdigit() else None
    if status is None:
        return HttpResponse('Choose a status.', status=400)
    try:
        services.move(lead, status)
    except ValidationError as exc:
        return HttpResponse(exc.messages[0], status=400)
    if request.POST.get('reload'):
        return _redirect(reverse('lead_detail', args=[lead.pk]))
    return HttpResponse(status=204)


@login_required
@require_permission('access_leads')
@require_POST
def lead_note_create(request, pk):
    lead = _lead_or_404(request.user, pk)
    form = LeadNoteForm(request.POST)
    if form.is_valid() and form.cleaned_data['body'].strip():
        LeadNote.objects.create(lead=lead, body=form.cleaned_data['body'].strip(), author=request.user)
        lead.save(update_fields=['updated_at'])
    return render(request, 'leads/partials/notes.html', {
        'lead': lead, 'notes': lead.lead_notes.select_related('author'), 'note_form': LeadNoteForm(),
    })


@login_required
@require_permission('access_leads')
@require_POST
def lead_note_delete(request, pk, note_pk):
    lead = _lead_or_404(request.user, pk)
    note = get_object_or_404(LeadNote, pk=note_pk, lead=lead)
    if note.author_id != request.user.pk and not request.user.is_admin:
        return HttpResponseForbidden('Only the author can delete this note.')
    note.delete()
    return render(request, 'leads/partials/notes.html', {
        'lead': lead, 'notes': lead.lead_notes.select_related('author'), 'note_form': LeadNoteForm(),
    })


@login_required
@require_permission('access_leads')
@require_POST
def lead_delete(request, pk):
    """Admins delete a lead with no estimates that never became a client (mistakes, spam)."""
    lead = _lead_or_404(request.user, pk)
    if not request.user.is_admin:
        return HttpResponseForbidden('Admin access required')
    if lead.is_converted:
        return HttpResponse('This lead is a client now. It stays for the history.', status=400)
    if lead.estimates.exists():
        return HttpResponse('This lead has estimates. Move it to Lost instead.', status=400)
    lead.delete()
    return _redirect(reverse('lead_list'))


@login_required
@require_permission('access_leads')
@require_permission('clients_create')
def lead_convert(request, pk):
    """Make the lead a client. From an accepted estimate (``?estimate=``) it then makes the invoice."""
    lead = _lead_or_404(request.user, pk)
    if lead.is_converted:
        return HttpResponse('This lead is already a client.', status=400)
    raw_estimate = request.POST.get('estimate') or request.GET.get('estimate') or ''
    estimates = lead.estimates.filter(client__isnull=True)
    from_estimate = estimates.filter(pk=raw_estimate).first() if raw_estimate.isdigit() else None
    project_estimate = (
        from_estimate
        or estimates.filter(accepted_at__isnull=False).order_by('-number').first()
        or estimates.order_by('-number').first()
    )
    can_invoice = (
        from_estimate is not None
        and from_estimate.accepted_at is not None
        and from_estimate.invoice_id is None
        and request.user.has_app_permission('access_invoices')
        and request.user.has_app_permission('invoices_create')
    )
    can_project = request.user.has_app_permission('access_projects') and request.user.has_app_permission(
        'projects_create',
    )
    form = ConvertForm(request.POST or None, user=request.user, lead=lead)
    if request.method == 'POST' and form.is_valid():
        existing = form.cleaned_data['client'] if form.cleaned_data['target'] == ConvertForm.EXISTING else None
        project_name = form.cleaned_data['project_name'] if (can_project and form.cleaned_data['create_project']) else ''
        try:
            client, project = services.convert(
                lead, user=request.user, client=existing, project_name=project_name,
                project_estimate=project_estimate,
            )
        except ValidationError as exc:
            form.add_error(None, exc.messages[0])
        else:
            if can_invoice:
                from apps.invoices.estimates import convert_to_invoice

                from_estimate.refresh_from_db()
                try:
                    invoice = convert_to_invoice(from_estimate)
                except ValidationError:
                    # The client is made; the estimate page says what is missing to invoice it.
                    return _redirect(reverse('estimate_detail', args=[from_estimate.pk]))
                return _redirect(reverse('invoice_detail', args=[invoice.pk]))
            return _redirect(reverse('client_detail', args=[client.pk]))
    return render(request, 'leads/partials/convert_drawer.html', {
        'lead': lead,
        'form': form,
        'from_estimate': from_estimate,
        'can_invoice': can_invoice,
        'can_project': can_project,
        'project_estimate': project_estimate,
    })
