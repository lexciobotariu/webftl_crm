from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .forms import ClientForm
from .models import Client

CLIENTS_PER_PAGE = 20


@login_required
def client_list(request):
    clients_qs = Client.objects.all().order_by('name')
    paginator = Paginator(clients_qs, CLIENTS_PER_PAGE)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'clients/client_list.html', {
        'clients': page_obj,
        'page_obj': page_obj,
        'total_count': paginator.count,
    })


@login_required
def client_create(request):
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save()
            if request.htmx:
                return render(request, 'clients/partials/client_card.html', {'client': client})
            return redirect('client_detail', pk=client.pk)
    else:
        form = ClientForm()
    return render(request, 'clients/client_form.html', {'form': form})


@login_required
def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk)
    return render(request, 'clients/client_detail.html', {'client': client})


@login_required
def client_edit(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            return redirect('client_detail', pk=client.pk)
    else:
        form = ClientForm(instance=client)
    return render(request, 'clients/client_form.html', {'form': form, 'client': client})


@login_required
def client_edit_drawer(request, pk):
    """Edit client profile via drawer (HTMX)."""
    client = get_object_or_404(Client, pk=pk)

    if request.method == 'POST':
        client.name = request.POST.get('name', client.name)
        client.email = request.POST.get('email', '') or None
        client.phone = request.POST.get('phone', '') or None
        client.address = request.POST.get('address', '') or None
        client.save()

        # Return updated profile content and close drawer
        response = render(request, 'clients/partials/profile_content.html', {'client': client})
        response['HX-Trigger'] = 'closeSlideOver, updateClientName'
        return response

    return render(request, 'clients/partials/edit_drawer.html', {'client': client})


@login_required
def client_edit_notes(request, pk):
    """Edit client notes inline (HTMX)."""
    client = get_object_or_404(Client, pk=pk)

    if request.method == 'POST':
        client.notes = request.POST.get('notes', '') or None
        client.save()
        return render(request, 'clients/partials/notes_display.html', {'client': client})

    return render(request, 'clients/partials/notes_edit.html', {'client': client})


@login_required
def client_notes_display(request, pk):
    """Return notes display partial (for cancel action)."""
    client = get_object_or_404(Client, pk=pk)
    return render(request, 'clients/partials/notes_display.html', {'client': client})


@login_required
@require_POST
def client_delete(request, pk):
    if not request.user.is_admin:
        return HttpResponseForbidden("Admin access required")
    client = get_object_or_404(Client, pk=pk)
    client.delete()
    if request.htmx:
        response = HttpResponse('')
        response['HX-Redirect'] = '/clients/'
        return response
    return redirect('client_list')
