import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone

from .forms import EmployeeSalaryForm
from .models import EmployeeSalary


def _set_salary_triggers(response, *, close=False):
    """Attach HX-Trigger header for HTMX updates."""
    triggers = {'refreshSalaryList': True}
    if close:
        triggers['closeSlideOver'] = True
    response['HX-Trigger'] = json.dumps(triggers)
    return response


@login_required
def salary_list(request):
    """List all employee salary configurations."""
    salaries = EmployeeSalary.objects.select_related('user').prefetch_related('months').all()

    now = timezone.now()
    current_year = now.year
    current_month = now.month

    salary_data = []
    for salary in salaries:
        current_month_entry = salary.months.filter(
            year=current_year, month=current_month
        ).first()
        salary_data.append({
            'salary': salary,
            'current_month': current_month_entry,
        })

    return render(request, 'salaries/salary_list.html', {
        'salary_data': salary_data,
        'current_year': current_year,
        'current_month': current_month,
    })


@login_required
def salary_create(request):
    """Create salary configuration for an employee."""
    if request.method == 'POST':
        form = EmployeeSalaryForm(request.POST)
        if form.is_valid():
            form.save()
            response = HttpResponse('')
            return _set_salary_triggers(response, close=True)
        return render(request, 'salaries/partials/create_salary_drawer.html', {'form': form})

    form = EmployeeSalaryForm()
    return render(request, 'salaries/partials/create_salary_drawer.html', {'form': form})


@login_required
def salary_detail(request, pk):
    """Employee salary detail page - placeholder."""
    return HttpResponse('<div class="p-4 text-zinc-400">Detail page coming soon</div>')
