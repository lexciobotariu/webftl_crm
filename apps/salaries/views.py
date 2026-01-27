from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from .models import EmployeeSalary


@login_required
def salary_list(request):
    """List all employee salary configurations."""
    salaries = EmployeeSalary.objects.select_related('user').prefetch_related('months').all()

    # Get current month info for each salary
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
    """Create salary configuration drawer - placeholder."""
    return HttpResponse('<div class="p-4 text-zinc-400">Create form coming soon</div>')


@login_required
def salary_detail(request, pk):
    """Employee salary detail page - placeholder."""
    return HttpResponse('<div class="p-4 text-zinc-400">Detail page coming soon</div>')
