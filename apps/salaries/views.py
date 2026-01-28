from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST

from . import services
from .forms import EmployeeSalaryForm, SalaryMonthForm, PaymentForm
from .models import EmployeeSalary, SalaryMonth, Payment


@login_required
def salary_list(request):
    """List all employee salary configurations."""
    salary_data, current_year, current_month, has_available_users, has_any_users = (
        services.get_salary_list_data()
    )
    return render(request, 'salaries/salary_list.html', {
        'salary_data': salary_data,
        'current_year': current_year,
        'current_month': current_month,
        'has_available_users': has_available_users,
        'has_any_users': has_any_users,
    })


@login_required
def salary_create(request):
    """Create salary configuration for an employee."""
    from django.contrib.auth import get_user_model
    User = get_user_model()

    # Only non-staff users are considered employees
    has_any_employees = User.objects.filter(is_staff=False).exists()

    if request.method == 'POST':
        form = EmployeeSalaryForm(request.POST)
        if form.is_valid():
            services.create_employee_salary(form)
            response = HttpResponse('')
            return services.set_salary_triggers(response, close=True)
        return render(request, 'salaries/partials/create_salary_drawer.html', {
            'form': form,
            'has_any_users': has_any_employees,
        })

    form = EmployeeSalaryForm()
    return render(request, 'salaries/partials/create_salary_drawer.html', {
        'form': form,
        'has_any_users': has_any_employees,
    })


@login_required
def salary_detail(request, pk):
    """Employee salary detail with month list."""
    try:
        salary, months, current_year, current_month = services.get_salary_detail_data(pk)
    except EmployeeSalary.DoesNotExist:
        from django.http import Http404
        raise Http404("Employee salary not found")

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
            services.create_salary_month(form)
            response = HttpResponse('')
            return services.set_salary_triggers(response, close=True)
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
            services.create_payment(form)
            response = HttpResponse('')
            return services.set_salary_triggers(response, close=True)
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
            services.update_employee_salary(form)
            response = HttpResponse('')
            return services.set_salary_triggers(response, close=True)
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
    services.delete_employee_salary(salary)
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
            services.update_salary_month(form)
            response = HttpResponse('')
            return services.set_salary_triggers(response, close=True)
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
    services.delete_salary_month(month)
    response = HttpResponse('')
    return services.set_salary_triggers(response, close=True)


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
            services.update_payment(form)
            response = HttpResponse('')
            return services.set_salary_triggers(response, close=True)
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
    services.delete_payment(payment)
    response = HttpResponse('')
    return services.set_salary_triggers(response, close=True)
