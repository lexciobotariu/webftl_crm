from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import EmployeeSalary


@login_required
def salary_list(request):
    """List all employee salary configurations."""
    salaries = EmployeeSalary.objects.select_related('user').all()
    return render(request, 'salaries/salary_list.html', {
        'salaries': salaries,
    })
