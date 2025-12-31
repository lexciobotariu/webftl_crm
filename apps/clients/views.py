from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .forms import ClientForm
from .models import Client


@login_required
def client_list(request):
    clients = Client.objects.all()
    return render(request, 'clients/client_list.html', {'clients': clients})


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
