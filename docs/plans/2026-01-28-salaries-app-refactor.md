# Salaries App Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the empty drawer bug and refactor the salaries app to follow the same architectural patterns as the tasks app (service layer, proper form initialization, comprehensive tests).

**Architecture:** Fix form initialization to preserve instance data when editing, then extract business logic from views into a service layer following the tasks app pattern. Views become thin orchestration layers that delegate to services.

**Tech Stack:** Django 5.x, pytest, HTMX, Alpine.js (existing stack)

---

## Task 1: Fix Form Initialization Bug (Critical - Fixes Empty Drawers)

**Files:**
- Modify: `apps/salaries/forms.py:69-81`
- Test: `apps/salaries/tests/test_forms.py` (new file)

**Step 1: Write the failing test for SalaryMonthForm edit initialization**

Create `apps/salaries/tests/test_forms.py`:

```python
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.salaries.forms import SalaryMonthForm, PaymentForm
from apps.salaries.models import EmployeeSalary, SalaryMonth, Payment

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email='employee@example.com',
        name='Test Employee',
        password='testpass123'
    )


@pytest.fixture
def employee_salary(user):
    return EmployeeSalary.objects.create(
        user=user,
        base_salary=Decimal('5000.00'),
        currency='EUR'
    )


@pytest.fixture
def salary_month(employee_salary):
    return SalaryMonth.objects.create(
        employee_salary=employee_salary,
        year=2024,
        month=6,
        expected_amount=Decimal('5500.00')
    )


@pytest.mark.django_db
class TestSalaryMonthFormInitialization:
    """Tests for SalaryMonthForm initialization behavior."""

    def test_create_form_prefills_current_date(self, employee_salary):
        """Test that create form prefills with current month/year."""
        form = SalaryMonthForm(employee_salary=employee_salary)
        now = timezone.now()

        assert form.initial['year'] == now.year
        assert form.initial['month'] == now.month

    def test_create_form_prefills_base_salary(self, employee_salary):
        """Test that create form prefills expected_amount with base salary."""
        form = SalaryMonthForm(employee_salary=employee_salary)

        assert form.initial['expected_amount'] == Decimal('5000.00')

    def test_edit_form_preserves_instance_values(self, employee_salary, salary_month):
        """Test that edit form preserves the instance's year/month values."""
        form = SalaryMonthForm(instance=salary_month, employee_salary=employee_salary)

        # Should preserve instance values, NOT override with current date
        assert form.initial.get('year', form.instance.year) == 2024
        assert form.initial.get('month', form.instance.month) == 6
        # The form.year.value should return the instance value
        assert form['year'].value() == 2024
        assert form['month'].value() == 6

    def test_edit_form_preserves_expected_amount(self, employee_salary, salary_month):
        """Test that edit form preserves the instance's expected_amount."""
        form = SalaryMonthForm(instance=salary_month, employee_salary=employee_salary)

        # Should preserve 5500.00, NOT override with base salary 5000.00
        assert form['expected_amount'].value() == Decimal('5500.00')
```

**Step 2: Run test to verify it fails**

Run: `pytest apps/salaries/tests/test_forms.py::TestSalaryMonthFormInitialization::test_edit_form_preserves_instance_values -v`

Expected: FAIL - form returns current year/month instead of 2024/6

**Step 3: Fix the SalaryMonthForm initialization**

Modify `apps/salaries/forms.py` lines 69-81. Change from:

```python
def __init__(self, *args, employee_salary=None, **kwargs):
    super().__init__(*args, **kwargs)
    self.employee_salary = employee_salary

    # Pre-fill with current date
    now = timezone.now()
    if not self.data:
        self.initial['year'] = now.year
        self.initial['month'] = now.month

    # Pre-fill expected_amount with base salary
    if employee_salary and not self.data:
        self.initial['expected_amount'] = employee_salary.base_salary
```

To:

```python
def __init__(self, *args, employee_salary=None, **kwargs):
    super().__init__(*args, **kwargs)
    self.employee_salary = employee_salary

    # Only pre-fill defaults for NEW records (not when editing)
    is_new = not self.instance.pk

    if is_new and not self.data:
        # Pre-fill with current date for new records
        now = timezone.now()
        self.initial['year'] = now.year
        self.initial['month'] = now.month

        # Pre-fill expected_amount with base salary for new records
        if employee_salary:
            self.initial['expected_amount'] = employee_salary.base_salary
```

**Step 4: Run test to verify it passes**

Run: `pytest apps/salaries/tests/test_forms.py -v`

Expected: All tests PASS

**Step 5: Run all existing salaries tests to ensure no regression**

Run: `pytest apps/salaries/tests/ -v`

Expected: All tests PASS

**Step 6: Commit**

```bash
git add apps/salaries/forms.py apps/salaries/tests/test_forms.py
git commit -m "$(cat <<'EOF'
fix(salaries): preserve instance values when editing month forms

The SalaryMonthForm was overwriting instance values with defaults
(current date, base salary) when editing existing records. This caused
edit drawers to appear empty or show wrong data.

Now only applies defaults for new records (when instance.pk is None).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add Test for PaymentForm Edit Initialization

**Files:**
- Modify: `apps/salaries/tests/test_forms.py`

**Step 1: Write the failing test for PaymentForm edit**

Add to `apps/salaries/tests/test_forms.py`:

```python
from datetime import date


@pytest.fixture
def payment(salary_month):
    return Payment.objects.create(
        salary_month=salary_month,
        amount=Decimal('2500.00'),
        payment_date=date(2024, 6, 15),
        payment_method='bank_transfer',
        notes='Test payment'
    )


@pytest.mark.django_db
class TestPaymentFormInitialization:
    """Tests for PaymentForm initialization behavior."""

    def test_create_form_prefills_today(self, employee_salary, salary_month):
        """Test that create form prefills payment_date with today."""
        form = PaymentForm(employee_salary=employee_salary)

        assert form.initial['payment_date'] == timezone.now().date()

    def test_edit_form_preserves_payment_date(self, employee_salary, payment):
        """Test that edit form preserves the instance's payment_date."""
        form = PaymentForm(instance=payment, employee_salary=employee_salary)

        # Should preserve 2024-06-15, NOT override with today
        assert form['payment_date'].value() == date(2024, 6, 15)

    def test_edit_form_preserves_all_values(self, employee_salary, payment):
        """Test that edit form preserves all instance values."""
        form = PaymentForm(instance=payment, employee_salary=employee_salary)

        assert form['amount'].value() == Decimal('2500.00')
        assert form['payment_method'].value() == 'bank_transfer'
        assert form['notes'].value() == 'Test payment'
```

**Step 2: Run test to verify current behavior**

Run: `pytest apps/salaries/tests/test_forms.py::TestPaymentFormInitialization -v`

Expected: Tests should PASS (PaymentForm only sets payment_date default, which doesn't override instance)

**Step 3: Verify PaymentForm is correct (no changes needed)**

The PaymentForm at line 150 uses:
```python
if not self.data:
    self.initial['payment_date'] = timezone.now().date()
```

This is safe because Django's form initialization respects instance values over initial values for existing records. But let's make it explicit for consistency.

Modify `apps/salaries/forms.py` lines 149-151. Change from:

```python
# Default payment_date to today
if not self.data:
    self.initial['payment_date'] = timezone.now().date()
```

To:

```python
# Default payment_date to today for new records only
is_new = not self.instance.pk
if is_new and not self.data:
    self.initial['payment_date'] = timezone.now().date()
```

**Step 4: Run tests to verify**

Run: `pytest apps/salaries/tests/test_forms.py -v`

Expected: All tests PASS

**Step 5: Commit**

```bash
git add apps/salaries/forms.py apps/salaries/tests/test_forms.py
git commit -m "$(cat <<'EOF'
fix(salaries): make PaymentForm initialization explicit for new records

Add explicit is_new check for consistency with SalaryMonthForm.
Add tests for PaymentForm initialization behavior.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Manual Verification of Drawer Fix

**Files:** None (manual testing)

**Step 1: Start the development server**

Run: `python manage.py runserver`

**Step 2: Test month edit drawer**

1. Navigate to salaries list
2. Click on an employee to view details
3. If no months exist, create one first
4. Click the edit button on a month entry
5. Verify the drawer shows the correct year, month, and expected amount

**Step 3: Test payment edit drawer**

1. On the same salary detail page
2. If no payments exist, create one first
3. Click the edit button on a payment entry
4. Verify the drawer shows the correct values (amount, date, method, notes)

**Step 4: Document results**

If drawers work correctly, proceed to Task 4.
If issues persist, investigate further before continuing.

---

## Task 4: Create Service Layer Structure

**Files:**
- Modify: `apps/salaries/services.py`

**Step 1: Write the service layer skeleton**

Replace contents of `apps/salaries/services.py`:

```python
"""
Service layer for salary operations.

This module contains business logic extracted from views.py.
Views should delegate to these functions for all salary-related operations.

Key patterns:
- Functions are organized by entity (EmployeeSalary, SalaryMonth, Payment)
- All functions that modify data return the modified instance
- HTMX trigger logic stays in views (presentation concern)
"""
import json
from django.http import HttpResponse


def set_salary_triggers(response, *, close=False):
    """
    Attach HX-Trigger header for HTMX updates.

    Args:
        response: HttpResponse to modify
        close: Whether to also trigger drawer close

    Returns:
        Modified HttpResponse with HX-Trigger header
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
    Get salary data for the list view.

    Returns:
        tuple: (salary_data list, has_available_users, has_any_users)
    """
    from django.contrib.auth import get_user_model
    from django.utils import timezone
    from .models import EmployeeSalary

    User = get_user_model()

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

    users_with_salary = EmployeeSalary.objects.values_list('user_id', flat=True)
    employee_users = User.objects.filter(is_staff=False)
    has_available_users = employee_users.exclude(id__in=users_with_salary).exists()
    has_any_users = employee_users.exists()

    return salary_data, current_year, current_month, has_available_users, has_any_users


def create_employee_salary(form):
    """
    Create a new employee salary configuration.

    Args:
        form: Valid EmployeeSalaryForm instance

    Returns:
        EmployeeSalary instance
    """
    return form.save()


def update_employee_salary(form):
    """
    Update an existing employee salary configuration.

    Args:
        form: Valid EmployeeSalaryForm instance with instance set

    Returns:
        EmployeeSalary instance
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
    Get data for salary detail view.

    Args:
        salary_pk: Primary key of EmployeeSalary

    Returns:
        tuple: (salary, months queryset, current_year, current_month)
    """
    from django.shortcuts import get_object_or_404
    from django.utils import timezone
    from .models import EmployeeSalary

    salary = get_object_or_404(
        EmployeeSalary.objects.select_related('user'),
        pk=salary_pk
    )
    months = salary.months.prefetch_related('payments').all()

    now = timezone.now()

    return salary, months, now.year, now.month


def create_salary_month(form):
    """
    Create a new salary month entry.

    Args:
        form: Valid SalaryMonthForm instance

    Returns:
        SalaryMonth instance
    """
    return form.save()


def update_salary_month(form):
    """
    Update an existing salary month entry.

    Args:
        form: Valid SalaryMonthForm instance with instance set

    Returns:
        SalaryMonth instance
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
    Create a new payment.

    Args:
        form: Valid PaymentForm instance

    Returns:
        Payment instance
    """
    return form.save()


def update_payment(form):
    """
    Update an existing payment.

    Args:
        form: Valid PaymentForm instance with instance set

    Returns:
        Payment instance
    """
    return form.save()


def delete_payment(payment):
    """
    Delete a payment.

    Args:
        payment: Payment instance to delete
    """
    payment.delete()
```

**Step 2: Run existing tests to ensure no breakage**

Run: `pytest apps/salaries/tests/ -v`

Expected: All tests PASS (services not yet used)

**Step 3: Commit**

```bash
git add apps/salaries/services.py
git commit -m "$(cat <<'EOF'
feat(salaries): add service layer structure

Create service layer following tasks app pattern.
Functions organized by entity (EmployeeSalary, SalaryMonth, Payment).
Views will be refactored to use these services in next commits.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Create Service Layer Tests

**Files:**
- Create: `apps/salaries/tests/test_services.py`

**Step 1: Write tests for service functions**

Create `apps/salaries/tests/test_services.py`:

```python
"""Tests for salaries service layer."""
import pytest
from decimal import Decimal
from datetime import date
from django.contrib.auth import get_user_model

from apps.salaries import services
from apps.salaries.models import EmployeeSalary, SalaryMonth, Payment
from apps.salaries.forms import EmployeeSalaryForm, SalaryMonthForm, PaymentForm

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email='employee@example.com',
        name='Test Employee',
        password='testpass123',
        is_staff=False
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        email='admin@example.com',
        name='Admin User',
        password='testpass123',
        is_staff=True
    )


@pytest.fixture
def employee_salary(user):
    return EmployeeSalary.objects.create(
        user=user,
        base_salary=Decimal('5000.00'),
        currency='EUR'
    )


@pytest.fixture
def salary_month(employee_salary):
    return SalaryMonth.objects.create(
        employee_salary=employee_salary,
        year=2025,
        month=1,
        expected_amount=Decimal('5000.00')
    )


@pytest.fixture
def payment(salary_month):
    return Payment.objects.create(
        salary_month=salary_month,
        amount=Decimal('2500.00'),
        payment_date=date(2025, 1, 15),
        payment_method='bank_transfer'
    )


@pytest.mark.django_db
class TestGetSalaryListData:
    """Tests for get_salary_list_data service."""

    def test_returns_salary_data(self, employee_salary):
        """Test that salary data is returned."""
        salary_data, _, _, _, _ = services.get_salary_list_data()

        assert len(salary_data) == 1
        assert salary_data[0]['salary'] == employee_salary

    def test_returns_current_month_entry(self, employee_salary):
        """Test that current month entry is included if exists."""
        from django.utils import timezone
        now = timezone.now()
        month = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=now.year,
            month=now.month,
            expected_amount=Decimal('5000.00')
        )

        salary_data, _, _, _, _ = services.get_salary_list_data()

        assert salary_data[0]['current_month'] == month

    def test_has_available_users_true(self, user):
        """Test has_available_users is True when user has no salary."""
        _, _, _, has_available, _ = services.get_salary_list_data()

        assert has_available is True

    def test_has_available_users_false(self, employee_salary):
        """Test has_available_users is False when all users have salary."""
        _, _, _, has_available, _ = services.get_salary_list_data()

        assert has_available is False

    def test_excludes_staff_from_available_users(self, admin_user):
        """Test that staff users are not counted as available employees."""
        _, _, _, has_available, has_any = services.get_salary_list_data()

        # Admin is staff, so no employees available
        assert has_available is False
        assert has_any is False


@pytest.mark.django_db
class TestEmployeeSalaryServices:
    """Tests for EmployeeSalary CRUD services."""

    def test_create_employee_salary(self, user):
        """Test creating employee salary via service."""
        form = EmployeeSalaryForm(data={
            'user': user.id,
            'base_salary': '6000.00',
            'currency': 'USD',
        })
        assert form.is_valid(), form.errors

        salary = services.create_employee_salary(form)

        assert salary.pk is not None
        assert salary.user == user
        assert salary.base_salary == Decimal('6000.00')

    def test_update_employee_salary(self, employee_salary):
        """Test updating employee salary via service."""
        form = EmployeeSalaryForm(
            data={
                'user': employee_salary.user.id,
                'base_salary': '5500.00',
                'currency': 'EUR',
            },
            instance=employee_salary
        )
        # Include current user in queryset for edit
        form.fields['user'].queryset = (
            form.fields['user'].queryset |
            User.objects.filter(pk=employee_salary.user.pk)
        )
        assert form.is_valid(), form.errors

        salary = services.update_employee_salary(form)

        assert salary.base_salary == Decimal('5500.00')

    def test_delete_employee_salary(self, employee_salary):
        """Test deleting employee salary via service."""
        salary_pk = employee_salary.pk

        services.delete_employee_salary(employee_salary)

        assert not EmployeeSalary.objects.filter(pk=salary_pk).exists()


@pytest.mark.django_db
class TestSalaryMonthServices:
    """Tests for SalaryMonth CRUD services."""

    def test_get_salary_detail_data(self, employee_salary, salary_month):
        """Test getting salary detail data."""
        salary, months, year, month = services.get_salary_detail_data(employee_salary.pk)

        assert salary == employee_salary
        assert salary_month in months
        assert isinstance(year, int)
        assert isinstance(month, int)

    def test_create_salary_month(self, employee_salary):
        """Test creating salary month via service."""
        form = SalaryMonthForm(
            data={
                'year': 2025,
                'month': 3,
                'expected_amount': '5000.00',
            },
            employee_salary=employee_salary
        )
        assert form.is_valid(), form.errors

        month = services.create_salary_month(form)

        assert month.pk is not None
        assert month.year == 2025
        assert month.month == 3

    def test_update_salary_month(self, employee_salary, salary_month):
        """Test updating salary month via service."""
        form = SalaryMonthForm(
            data={
                'year': 2025,
                'month': 1,
                'expected_amount': '5500.00',
            },
            instance=salary_month,
            employee_salary=employee_salary
        )
        assert form.is_valid(), form.errors

        month = services.update_salary_month(form)

        assert month.expected_amount == Decimal('5500.00')

    def test_delete_salary_month(self, salary_month):
        """Test deleting salary month via service."""
        month_pk = salary_month.pk

        services.delete_salary_month(salary_month)

        assert not SalaryMonth.objects.filter(pk=month_pk).exists()


@pytest.mark.django_db
class TestPaymentServices:
    """Tests for Payment CRUD services."""

    def test_create_payment(self, employee_salary, salary_month):
        """Test creating payment via service."""
        form = PaymentForm(
            data={
                'salary_month': salary_month.id,
                'amount': '1000.00',
                'payment_date': '2025-01-20',
                'payment_method': 'cash',
            },
            employee_salary=employee_salary
        )
        assert form.is_valid(), form.errors

        payment = services.create_payment(form)

        assert payment.pk is not None
        assert payment.amount == Decimal('1000.00')

    def test_update_payment(self, employee_salary, payment):
        """Test updating payment via service."""
        form = PaymentForm(
            data={
                'salary_month': payment.salary_month.id,
                'amount': '3000.00',
                'payment_date': '2025-01-16',
                'payment_method': 'bank_transfer',
            },
            instance=payment,
            employee_salary=employee_salary
        )
        assert form.is_valid(), form.errors

        updated = services.update_payment(form)

        assert updated.amount == Decimal('3000.00')

    def test_delete_payment(self, payment):
        """Test deleting payment via service."""
        payment_pk = payment.pk

        services.delete_payment(payment)

        assert not Payment.objects.filter(pk=payment_pk).exists()
```

**Step 2: Run tests to verify they pass**

Run: `pytest apps/salaries/tests/test_services.py -v`

Expected: All tests PASS

**Step 3: Commit**

```bash
git add apps/salaries/tests/test_services.py
git commit -m "$(cat <<'EOF'
test(salaries): add comprehensive service layer tests

Test all CRUD operations through service functions.
Verify data retrieval functions return correct data.
Test edge cases like staff user exclusion.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Refactor Views to Use Services

**Files:**
- Modify: `apps/salaries/views.py`

**Step 1: Refactor salary_list view**

Modify `apps/salaries/views.py`. Replace the `_set_salary_triggers` function and `salary_list` view (lines 13-57):

```python
import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST

from .forms import EmployeeSalaryForm, SalaryMonthForm, PaymentForm
from .models import EmployeeSalary, SalaryMonth, Payment
from . import services


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
```

**Step 2: Refactor salary_create view**

Replace `salary_create` view (lines 60-84):

```python
@login_required
def salary_create(request):
    """Create salary configuration for an employee."""
    from django.contrib.auth import get_user_model
    User = get_user_model()

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
```

**Step 3: Refactor salary_detail view**

Replace `salary_detail` view (lines 87-105):

```python
@login_required
def salary_detail(request, pk):
    """Employee salary detail with month list."""
    salary, months, current_year, current_month = services.get_salary_detail_data(pk)

    return render(request, 'salaries/salary_detail.html', {
        'salary': salary,
        'months': months,
        'current_year': current_year,
        'current_month': current_month,
    })
```

**Step 4: Refactor month_create view**

Replace `month_create` view (lines 108-131):

```python
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
```

**Step 5: Refactor payment_create view**

Replace `payment_create` view (lines 134-157):

```python
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
```

**Step 6: Refactor salary_edit view**

Replace `salary_edit` view (lines 164-191):

```python
@login_required
def salary_edit(request, pk):
    """Edit salary configuration drawer."""
    salary = get_object_or_404(
        EmployeeSalary.objects.select_related('user'),
        pk=pk
    )

    if request.method == 'POST':
        form = EmployeeSalaryForm(request.POST, instance=salary)
        form.fields['user'].queryset = (
            form.fields['user'].queryset |
            salary.user.__class__.objects.filter(pk=salary.user.pk)
        )
        if form.is_valid():
            services.update_employee_salary(form)
            response = HttpResponse('')
            return services.set_salary_triggers(response, close=True)
        return render(request, 'salaries/partials/edit_salary_drawer.html', {
            'form': form,
            'salary': salary,
        })

    form = EmployeeSalaryForm(instance=salary)
    form.fields['user'].queryset = (
        form.fields['user'].queryset |
        salary.user.__class__.objects.filter(pk=salary.user.pk)
    )
    return render(request, 'salaries/partials/edit_salary_drawer.html', {
        'form': form,
        'salary': salary,
    })
```

**Step 7: Refactor salary_delete view**

Replace `salary_delete` view (lines 194-202):

```python
@login_required
@require_POST
def salary_delete(request, pk):
    """Delete salary configuration."""
    salary = get_object_or_404(EmployeeSalary, pk=pk)
    services.delete_employee_salary(salary)
    response = HttpResponse('')
    response['HX-Redirect'] = '/salaries/'
    return response
```

**Step 8: Refactor month_edit view**

Replace `month_edit` view (lines 209-235):

```python
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
```

**Step 9: Refactor month_delete view**

Replace `month_delete` view (lines 238-246):

```python
@login_required
@require_POST
def month_delete(request, pk, month_pk):
    """Delete month entry."""
    employee_salary = get_object_or_404(EmployeeSalary, pk=pk)
    month = get_object_or_404(SalaryMonth, pk=month_pk, employee_salary=employee_salary)
    services.delete_salary_month(month)
    response = HttpResponse('')
    return services.set_salary_triggers(response, close=True)
```

**Step 10: Refactor payment_edit view**

Replace `payment_edit` view (lines 253-283):

```python
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
```

**Step 11: Refactor payment_delete view**

Replace `payment_delete` view (lines 286-298):

```python
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
```

**Step 12: Run all tests**

Run: `pytest apps/salaries/tests/ -v`

Expected: All tests PASS

**Step 13: Commit**

```bash
git add apps/salaries/views.py
git commit -m "$(cat <<'EOF'
refactor(salaries): use service layer in views

Views now delegate to service functions for all operations.
This separates concerns: views handle HTTP, services handle business logic.
Pattern matches the tasks app architecture.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Final Integration Test

**Files:** None (manual + automated testing)

**Step 1: Run full test suite**

Run: `pytest apps/salaries/tests/ -v --tb=short`

Expected: All tests PASS

**Step 2: Run the development server**

Run: `python manage.py runserver`

**Step 3: Manual smoke test**

Test all CRUD operations:
1. Create a new employee salary
2. Edit the employee salary
3. Create a month entry
4. Edit the month entry (verify drawer shows correct values!)
5. Create a payment
6. Edit the payment (verify drawer shows correct values!)
7. Delete a payment
8. Delete a month
9. Delete the salary

**Step 4: Verify no regressions**

Run: `pytest -v --tb=short`

Expected: Full test suite PASS

**Step 5: Final commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
chore(salaries): complete refactor with service layer

Refactored salaries app to follow tasks app architecture:
- Fixed form initialization bug causing empty edit drawers
- Added comprehensive service layer
- Added form and service tests
- Views now thin orchestration layer

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

| Task | Description | Files Changed |
|------|-------------|---------------|
| 1 | Fix form initialization bug | `forms.py`, `tests/test_forms.py` |
| 2 | Add PaymentForm tests | `forms.py`, `tests/test_forms.py` |
| 3 | Manual verification | None |
| 4 | Create service layer | `services.py` |
| 5 | Add service tests | `tests/test_services.py` |
| 6 | Refactor views | `views.py` |
| 7 | Integration testing | None |

**Total new test coverage:** ~200 lines of tests for forms and services
