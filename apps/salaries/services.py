"""
Service layer for salary operations.

This module contains business logic extracted from views.py.
Views should delegate to these functions for all salary-related operations.

Key patterns:
- Data retrieval functions return tuples with all context needed by views
- CRUD operations accept validated forms and return the created/updated instance
- set_salary_triggers() handles HTMX response headers for UI updates
"""
import json

from django.contrib.auth import get_user_model
from django.db.models import Prefetch, Sum
from django.utils import timezone

from .models import EmployeeSalary, SalaryMonth

# =============================================================================
# Response Helpers
# =============================================================================

def set_salary_triggers(response, *, close=False):
    """
    Attach HX-Trigger header for HTMX updates.

    Args:
        response: HttpResponse to modify
        close: If True, also trigger closeSlideOver event

    Returns:
        The modified response with HX-Trigger header
    """
    triggers = {'refreshSalaryList': True}
    if close:
        triggers['closeSlideOver'] = True
    response['HX-Trigger'] = json.dumps(triggers)
    return response


# =============================================================================
# EmployeeSalary Services
# =============================================================================

def get_salary_list_data():
    """
    Get all data needed for the salary list view.

    Returns:
        Tuple of (salary_data, current_year, current_month, has_available_users, has_any_users)
        - salary_data: List of dicts with 'salary' and 'current_month' keys
        - current_year: Current year (int)
        - current_month: Current month 1-12 (int)
        - has_available_users: True if non-staff users without salary configs exist
        - has_any_users: True if any non-staff users exist
    """
    User = get_user_model()

    now = timezone.now()
    current_year = now.year
    current_month = now.month

    current_month_qs = SalaryMonth.objects.filter(
        year=current_year, month=current_month
    ).annotate(total_paid_sum=Sum('payments__amount'))

    salaries = EmployeeSalary.objects.select_related('user').prefetch_related(
        Prefetch('months', queryset=current_month_qs)
    )

    salary_data = []
    for salary in salaries:
        months = list(salary.months.all())
        current_month_entry = months[0] if months else None
        salary_data.append({
            'salary': salary,
            'current_month': current_month_entry,
        })

    # Check if there are users available (non-staff users without salary configs)
    users_with_salary = EmployeeSalary.objects.values_list('user_id', flat=True)
    employee_users = User.objects.filter(is_staff=False)
    has_available_users = employee_users.exclude(id__in=users_with_salary).exists()
    has_any_users = employee_users.exists()

    return salary_data, current_year, current_month, has_available_users, has_any_users


def create_employee_salary(form):
    """
    Create a new employee salary configuration from a validated form.

    Args:
        form: Validated EmployeeSalaryForm instance

    Returns:
        The created EmployeeSalary instance
    """
    return form.save()


def update_employee_salary(form):
    """
    Update an existing employee salary configuration from a validated form.

    Args:
        form: Validated EmployeeSalaryForm instance with instance set

    Returns:
        The updated EmployeeSalary instance
    """
    return form.save()


def delete_employee_salary(salary):
    """
    Delete an employee salary configuration.

    Args:
        salary: EmployeeSalary instance to delete
    """
    salary.delete()


# =============================================================================
# SalaryMonth Services
# =============================================================================

def get_salary_detail_data(salary_pk):
    """
    Get all data needed for the salary detail view.

    Args:
        salary_pk: Primary key of the EmployeeSalary

    Returns:
        Tuple of (salary, months, current_year, current_month)
        - salary: EmployeeSalary instance with user prefetched
        - months: QuerySet of SalaryMonth with payments prefetched
        - current_year: Current year (int)
        - current_month: Current month 1-12 (int)

    Raises:
        EmployeeSalary.DoesNotExist: If salary with given pk not found
    """
    salary = EmployeeSalary.objects.select_related('user').get(pk=salary_pk)
    months = (
        salary.months.prefetch_related('payments')
        .annotate(total_paid_sum=Sum('payments__amount'))
        .all()
    )

    now = timezone.now()
    current_year = now.year
    current_month = now.month

    return salary, months, current_year, current_month


def create_salary_month(form):
    """
    Create a new salary month entry from a validated form.

    Args:
        form: Validated SalaryMonthForm instance

    Returns:
        The created SalaryMonth instance
    """
    return form.save()


def update_salary_month(form):
    """
    Update an existing salary month entry from a validated form.

    Args:
        form: Validated SalaryMonthForm instance with instance set

    Returns:
        The updated SalaryMonth instance
    """
    return form.save()


def delete_salary_month(month):
    """
    Delete a salary month entry.

    Args:
        month: SalaryMonth instance to delete
    """
    month.delete()


# =============================================================================
# Payment Services
# =============================================================================

def create_payment(form):
    """
    Create a new payment from a validated form.

    Args:
        form: Validated PaymentForm instance

    Returns:
        The created Payment instance
    """
    return form.save()


def update_payment(form):
    """
    Update an existing payment from a validated form.

    Args:
        form: Validated PaymentForm instance with instance set

    Returns:
        The updated Payment instance
    """
    return form.save()


def delete_payment(payment):
    """
    Delete a payment.

    Args:
        payment: Payment instance to delete
    """
    payment.delete()
