import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import EmployeeSalaryForm, SalaryMonthForm, PaymentForm
from .models import EmployeeSalary, SalaryMonth, Payment


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
    """Employee salary detail with month list."""
    salary = get_object_or_404(
        EmployeeSalary.objects.select_related('user'),
        pk=pk
    )
    months = salary.months.prefetch_related('payments').all()

    now = timezone.now()
    current_year = now.year
    current_month = now.month

    return render(request, 'salaries/salary_detail.html', {
        'salary': salary,
        'months': months,
        'current_year': current_year,
        'current_month': current_month,
    })


@login_required
def month_create(request, pk):
    """Create month entry drawer."""
    employee_salary = get_object_or_404(
        EmployeeSalary.objects.select_related('user'),
        pk=pk
    )

    if request.method == 'POST':
        form = SalaryMonthForm(request.POST, employee_salary=employee_salary)
        if form.is_valid():
            form.save()
            response = HttpResponse('')
            return _set_salary_triggers(response, close=True)
        return render(request, 'salaries/partials/create_month_drawer.html', {
            'form': form,
            'employee_salary': employee_salary,
        })

    form = SalaryMonthForm(employee_salary=employee_salary)
    return render(request, 'salaries/partials/create_month_drawer.html', {
        'form': form,
        'employee_salary': employee_salary,
    })


@login_required
def payment_create(request, pk):
    """Record payment drawer."""
    employee_salary = get_object_or_404(
        EmployeeSalary.objects.select_related('user'),
        pk=pk
    )

    if request.method == 'POST':
        form = PaymentForm(request.POST, employee_salary=employee_salary)
        if form.is_valid():
            form.save()
            response = HttpResponse('')
            return _set_salary_triggers(response, close=True)
        return render(request, 'salaries/partials/create_payment_drawer.html', {
            'form': form,
            'employee_salary': employee_salary,
        })

    form = PaymentForm(employee_salary=employee_salary)
    return render(request, 'salaries/partials/create_payment_drawer.html', {
        'form': form,
        'employee_salary': employee_salary,
    })


# ============================================================================
# Employee Salary CRUD
# ============================================================================

@login_required
def salary_edit(request, pk):
    """Edit salary configuration drawer."""
    salary = get_object_or_404(
        EmployeeSalary.objects.select_related('user'),
        pk=pk
    )

    if request.method == 'POST':
        form = EmployeeSalaryForm(request.POST, instance=salary)
        # When editing, we need to allow the current user
        form.fields['user'].queryset = form.fields['user'].queryset | salary.user.__class__.objects.filter(pk=salary.user.pk)
        if form.is_valid():
            form.save()
            response = HttpResponse('')
            return _set_salary_triggers(response, close=True)
        return render(request, 'salaries/partials/edit_salary_drawer.html', {
            'form': form,
            'salary': salary,
        })

    form = EmployeeSalaryForm(instance=salary)
    # When editing, we need to allow the current user
    form.fields['user'].queryset = form.fields['user'].queryset | salary.user.__class__.objects.filter(pk=salary.user.pk)
    return render(request, 'salaries/partials/edit_salary_drawer.html', {
        'form': form,
        'salary': salary,
    })


@login_required
@require_POST
def salary_delete(request, pk):
    """Delete salary configuration."""
    salary = get_object_or_404(EmployeeSalary, pk=pk)
    salary.delete()
    response = HttpResponse('')
    response['HX-Redirect'] = '/salaries/'
    return response


# ============================================================================
# Salary Month CRUD
# ============================================================================

@login_required
def month_edit(request, pk, month_pk):
    """Edit month entry drawer."""
    employee_salary = get_object_or_404(
        EmployeeSalary.objects.select_related('user'),
        pk=pk
    )
    month = get_object_or_404(SalaryMonth, pk=month_pk, employee_salary=employee_salary)

    if request.method == 'POST':
        form = SalaryMonthForm(request.POST, instance=month, employee_salary=employee_salary)
        if form.is_valid():
            form.save()
            response = HttpResponse('')
            return _set_salary_triggers(response, close=True)
        return render(request, 'salaries/partials/edit_month_drawer.html', {
            'form': form,
            'employee_salary': employee_salary,
            'month': month,
        })

    form = SalaryMonthForm(instance=month, employee_salary=employee_salary)
    return render(request, 'salaries/partials/edit_month_drawer.html', {
        'form': form,
        'employee_salary': employee_salary,
        'month': month,
    })


@login_required
@require_POST
def month_delete(request, pk, month_pk):
    """Delete month entry."""
    employee_salary = get_object_or_404(EmployeeSalary, pk=pk)
    month = get_object_or_404(SalaryMonth, pk=month_pk, employee_salary=employee_salary)
    month.delete()
    response = HttpResponse('')
    return _set_salary_triggers(response, close=True)


# ============================================================================
# Payment CRUD
# ============================================================================

@login_required
def payment_edit(request, pk, payment_pk):
    """Edit payment drawer."""
    employee_salary = get_object_or_404(
        EmployeeSalary.objects.select_related('user'),
        pk=pk
    )
    payment = get_object_or_404(
        Payment.objects.select_related('salary_month'),
        pk=payment_pk,
        salary_month__employee_salary=employee_salary
    )

    if request.method == 'POST':
        form = PaymentForm(request.POST, instance=payment, employee_salary=employee_salary)
        if form.is_valid():
            form.save()
            response = HttpResponse('')
            return _set_salary_triggers(response, close=True)
        return render(request, 'salaries/partials/edit_payment_drawer.html', {
            'form': form,
            'employee_salary': employee_salary,
            'payment': payment,
        })

    form = PaymentForm(instance=payment, employee_salary=employee_salary)
    return render(request, 'salaries/partials/edit_payment_drawer.html', {
        'form': form,
        'employee_salary': employee_salary,
        'payment': payment,
    })


@login_required
@require_POST
def payment_delete(request, pk, payment_pk):
    """Delete payment."""
    employee_salary = get_object_or_404(EmployeeSalary, pk=pk)
    payment = get_object_or_404(
        Payment,
        pk=payment_pk,
        salary_month__employee_salary=employee_salary
    )
    payment.delete()
    response = HttpResponse('')
    return _set_salary_triggers(response, close=True)
