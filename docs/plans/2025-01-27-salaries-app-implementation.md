# Salaries App Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a standalone employee salary tracking app under a new "Finances" category in the sidebar.

**Architecture:** Django app with models for EmployeeSalary, SalaryMonth, and Payment. Uses HTMX for drawer interactions, Alpine.js for expandable lists. Service layer for business logic.

**Tech Stack:** Django 4.x, HTMX, Alpine.js, Tailwind CSS, pytest

---

## Task 1: Create Django App Scaffolding

**Files:**
- Create: `apps/salaries/__init__.py`
- Create: `apps/salaries/apps.py`
- Create: `apps/salaries/admin.py`
- Create: `apps/salaries/models.py`
- Create: `apps/salaries/views.py`
- Create: `apps/salaries/urls.py`
- Create: `apps/salaries/forms.py`
- Create: `apps/salaries/services.py`
- Create: `apps/salaries/tests/__init__.py`
- Modify: `config/settings.py:32-38`

**Step 1: Create the app directory and files**

```bash
mkdir -p apps/salaries/tests
touch apps/salaries/__init__.py
touch apps/salaries/tests/__init__.py
```

**Step 2: Create apps.py**

Create `apps/salaries/apps.py`:
```python
from django.apps import AppConfig


class SalariesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.salaries'
```

**Step 3: Create empty placeholder files**

Create `apps/salaries/admin.py`:
```python
from django.contrib import admin

# Models will be registered here after creation
```

Create `apps/salaries/models.py`:
```python
from django.conf import settings
from django.db import models

# Models will be defined in Task 2
```

Create `apps/salaries/views.py`:
```python
from django.contrib.auth.decorators import login_required

# Views will be defined in later tasks
```

Create `apps/salaries/urls.py`:
```python
from django.urls import path

from . import views

urlpatterns = []
```

Create `apps/salaries/forms.py`:
```python
from django import forms

# Forms will be defined in later tasks
```

Create `apps/salaries/services.py`:
```python
"""
Service layer for salary operations.
"""

# Service functions will be defined in later tasks
```

**Step 4: Register app in settings**

In `config/settings.py`, add `'apps.salaries',` after `'apps.notes',` (around line 37):
```python
INSTALLED_APPS = [
    # ... existing apps ...
    'apps.notes',
    'apps.salaries',
    'apps.integrations',
]
```

**Step 5: Verify setup**

Run: `python manage.py check`
Expected: System check identified no issues.

**Step 6: Commit**

```bash
git add apps/salaries/ config/settings.py
git commit -m "feat(salaries): add app scaffolding"
```

---

## Task 2: Create Models

**Files:**
- Modify: `apps/salaries/models.py`
- Create: `apps/salaries/tests/test_models.py`

**Step 1: Write failing tests for EmployeeSalary model**

Create `apps/salaries/tests/test_models.py`:
```python
import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model

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


class TestEmployeeSalaryModel:
    def test_create_employee_salary(self, user):
        """Test creating an employee salary configuration."""
        salary = EmployeeSalary.objects.create(
            user=user,
            base_salary=Decimal('5000.00'),
            currency='EUR'
        )
        assert salary.user == user
        assert salary.base_salary == Decimal('5000.00')
        assert salary.currency == 'EUR'
        assert str(salary) == f'{user.name} - 5000.00 EUR'

    def test_user_unique_constraint(self, employee_salary, user):
        """Test that a user can only have one salary configuration."""
        with pytest.raises(Exception):  # IntegrityError
            EmployeeSalary.objects.create(
                user=user,
                base_salary=Decimal('6000.00'),
                currency='USD'
            )

    def test_currency_choices(self, user):
        """Test currency choices are valid."""
        for currency in ['USD', 'EUR', 'GBP']:
            salary = EmployeeSalary(user=user, base_salary=Decimal('1000'), currency=currency)
            salary.full_clean()  # Should not raise


class TestSalaryMonthModel:
    def test_create_salary_month(self, employee_salary):
        """Test creating a salary month entry."""
        month = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        assert month.year == 2025
        assert month.month == 1
        assert month.expected_amount == Decimal('5000.00')
        assert str(month) == 'Test Employee - January 2025'

    def test_unique_year_month_constraint(self, employee_salary):
        """Test that year/month combination is unique per employee."""
        SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        with pytest.raises(Exception):  # IntegrityError
            SalaryMonth.objects.create(
                employee_salary=employee_salary,
                year=2025,
                month=1,
                expected_amount=Decimal('5500.00')
            )

    def test_total_paid_no_payments(self, employee_salary):
        """Test total_paid returns 0 when no payments exist."""
        month = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        assert month.total_paid == Decimal('0')

    def test_total_paid_with_payments(self, employee_salary):
        """Test total_paid sums all payments."""
        month = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        Payment.objects.create(
            salary_month=month,
            amount=Decimal('2000.00'),
            payment_date='2025-01-15',
            payment_method='bank_transfer'
        )
        Payment.objects.create(
            salary_month=month,
            amount=Decimal('1500.00'),
            payment_date='2025-01-25',
            payment_method='cash'
        )
        assert month.total_paid == Decimal('3500.00')

    def test_remaining_amount(self, employee_salary):
        """Test remaining calculation."""
        month = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        Payment.objects.create(
            salary_month=month,
            amount=Decimal('3000.00'),
            payment_date='2025-01-15',
            payment_method='bank_transfer'
        )
        assert month.remaining == Decimal('2000.00')

    def test_remaining_amount_overpaid(self, employee_salary):
        """Test remaining is 0 when overpaid (not negative)."""
        month = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        Payment.objects.create(
            salary_month=month,
            amount=Decimal('6000.00'),
            payment_date='2025-01-15',
            payment_method='bank_transfer'
        )
        assert month.remaining == Decimal('0')

    def test_bonus_amount(self, employee_salary):
        """Test bonus calculation when overpaid."""
        month = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        Payment.objects.create(
            salary_month=month,
            amount=Decimal('5500.00'),
            payment_date='2025-01-15',
            payment_method='bank_transfer'
        )
        assert month.bonus_amount == Decimal('500.00')

    def test_bonus_amount_no_overpayment(self, employee_salary):
        """Test bonus is 0 when not overpaid."""
        month = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        Payment.objects.create(
            salary_month=month,
            amount=Decimal('4000.00'),
            payment_date='2025-01-15',
            payment_method='bank_transfer'
        )
        assert month.bonus_amount == Decimal('0')

    def test_status_unpaid(self, employee_salary):
        """Test status is 'unpaid' when no payments."""
        month = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        assert month.status == 'unpaid'

    def test_status_partial(self, employee_salary):
        """Test status is 'partial' when partially paid."""
        month = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        Payment.objects.create(
            salary_month=month,
            amount=Decimal('2000.00'),
            payment_date='2025-01-15',
            payment_method='bank_transfer'
        )
        assert month.status == 'partial'

    def test_status_paid(self, employee_salary):
        """Test status is 'paid' when exactly paid."""
        month = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        Payment.objects.create(
            salary_month=month,
            amount=Decimal('5000.00'),
            payment_date='2025-01-15',
            payment_method='bank_transfer'
        )
        assert month.status == 'paid'

    def test_status_bonus(self, employee_salary):
        """Test status is 'bonus' when overpaid."""
        month = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        Payment.objects.create(
            salary_month=month,
            amount=Decimal('5500.00'),
            payment_date='2025-01-15',
            payment_method='bank_transfer'
        )
        assert month.status == 'bonus'

    def test_payment_count(self, employee_salary):
        """Test payment_count property."""
        month = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        Payment.objects.create(
            salary_month=month,
            amount=Decimal('2000.00'),
            payment_date='2025-01-15',
            payment_method='bank_transfer'
        )
        Payment.objects.create(
            salary_month=month,
            amount=Decimal('1500.00'),
            payment_date='2025-01-25',
            payment_method='cash'
        )
        assert month.payment_count == 2


class TestPaymentModel:
    def test_create_payment(self, employee_salary):
        """Test creating a payment."""
        month = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        payment = Payment.objects.create(
            salary_month=month,
            amount=Decimal('2500.00'),
            payment_date='2025-01-15',
            payment_method='bank_transfer',
            notes='January first payment'
        )
        assert payment.amount == Decimal('2500.00')
        assert payment.payment_method == 'bank_transfer'
        assert payment.notes == 'January first payment'
        assert str(payment) == '2500.00 on 15/01/2025'

    def test_payment_method_choices(self, employee_salary):
        """Test payment method choices are valid."""
        month = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        for method in ['cash', 'bank_transfer', 'check', 'other']:
            payment = Payment(
                salary_month=month,
                amount=Decimal('100'),
                payment_date='2025-01-15',
                payment_method=method
            )
            payment.full_clean()  # Should not raise
```

**Step 2: Run tests to verify they fail**

Run: `pytest apps/salaries/tests/test_models.py -v`
Expected: FAIL (models not defined yet)

**Step 3: Implement the models**

Replace `apps/salaries/models.py`:
```python
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum


class EmployeeSalary(models.Model):
    """Salary configuration for an employee (User)."""

    CURRENCY_CHOICES = [
        ('USD', 'USD ($)'),
        ('EUR', 'EUR (€)'),
        ('GBP', 'GBP (£)'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='salary_config'
    )
    base_salary = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='EUR')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Employee salaries'
        ordering = ['user__name']

    def __str__(self):
        return f'{self.user.name} - {self.base_salary} {self.currency}'


class SalaryMonth(models.Model):
    """A specific month's salary record for an employee."""

    MONTH_NAMES = [
        '', 'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ]

    employee_salary = models.ForeignKey(
        EmployeeSalary,
        on_delete=models.CASCADE,
        related_name='months'
    )
    year = models.PositiveIntegerField()
    month = models.PositiveIntegerField()  # 1-12
    expected_amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['employee_salary', 'year', 'month']
        ordering = ['-year', '-month']

    def __str__(self):
        month_name = self.MONTH_NAMES[self.month]
        return f'{self.employee_salary.user.name} - {month_name} {self.year}'

    @property
    def total_paid(self):
        """Sum of all payments for this month."""
        result = self.payments.aggregate(total=Sum('amount'))['total']
        return result or Decimal('0')

    @property
    def remaining(self):
        """Amount still owed (0 if overpaid)."""
        diff = self.expected_amount - self.total_paid
        return max(diff, Decimal('0'))

    @property
    def bonus_amount(self):
        """Amount paid over expected (0 if not overpaid)."""
        diff = self.total_paid - self.expected_amount
        return max(diff, Decimal('0'))

    @property
    def status(self):
        """Payment status: unpaid, partial, paid, or bonus."""
        total = self.total_paid
        if total == Decimal('0'):
            return 'unpaid'
        elif total < self.expected_amount:
            return 'partial'
        elif total == self.expected_amount:
            return 'paid'
        else:
            return 'bonus'

    @property
    def payment_count(self):
        """Number of payments for this month."""
        return self.payments.count()


class Payment(models.Model):
    """Individual payment transaction."""

    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('bank_transfer', 'Bank Transfer'),
        ('check', 'Check'),
        ('other', 'Other'),
    ]

    salary_month = models.ForeignKey(
        SalaryMonth,
        on_delete=models.CASCADE,
        related_name='payments'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date', '-created_at']

    def __str__(self):
        return f'{self.amount} on {self.payment_date.strftime("%d/%m/%Y")}'
```

**Step 4: Create migration**

Run: `python manage.py makemigrations salaries`
Expected: Creates migration file

**Step 5: Apply migration**

Run: `python manage.py migrate`
Expected: Migrations applied successfully

**Step 6: Run tests to verify they pass**

Run: `pytest apps/salaries/tests/test_models.py -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add apps/salaries/
git commit -m "feat(salaries): add EmployeeSalary, SalaryMonth, and Payment models"
```

---

## Task 3: Register Models in Admin

**Files:**
- Modify: `apps/salaries/admin.py`

**Step 1: Update admin.py**

Replace `apps/salaries/admin.py`:
```python
from django.contrib import admin

from .models import EmployeeSalary, SalaryMonth, Payment


class SalaryMonthInline(admin.TabularInline):
    model = SalaryMonth
    extra = 0
    fields = ['year', 'month', 'expected_amount']
    readonly_fields = ['created_at']


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = ['amount', 'payment_date', 'payment_method', 'notes']
    readonly_fields = ['created_at']


@admin.register(EmployeeSalary)
class EmployeeSalaryAdmin(admin.ModelAdmin):
    list_display = ['user', 'base_salary', 'currency', 'created_at']
    list_filter = ['currency']
    search_fields = ['user__name', 'user__email']
    raw_id_fields = ['user']
    inlines = [SalaryMonthInline]


@admin.register(SalaryMonth)
class SalaryMonthAdmin(admin.ModelAdmin):
    list_display = ['employee_salary', 'year', 'month', 'expected_amount', 'status', 'payment_count']
    list_filter = ['year', 'month', 'employee_salary__currency']
    search_fields = ['employee_salary__user__name']
    inlines = [PaymentInline]

    def status(self, obj):
        return obj.status

    def payment_count(self, obj):
        return obj.payment_count


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['salary_month', 'amount', 'payment_date', 'payment_method', 'created_at']
    list_filter = ['payment_method', 'payment_date']
    search_fields = ['salary_month__employee_salary__user__name', 'notes']
    date_hierarchy = 'payment_date'
```

**Step 2: Verify admin works**

Run: `python manage.py check`
Expected: System check identified no issues.

**Step 3: Commit**

```bash
git add apps/salaries/admin.py
git commit -m "feat(salaries): register models in Django admin"
```

---

## Task 4: Update Sidebar with Finances Category

**Files:**
- Modify: `templates/components/sidebar.html`

**Step 1: Add Finances category with Salaries link**

In `templates/components/sidebar.html`, add after the "My Tasks" link (around line 56) and before the Team admin section:

```html
        <!-- Finances -->
        <div class="mt-4 pt-3 border-t border-border-subtle">
            <span class="px-3 text-[10px] uppercase tracking-wider text-zinc-600 font-medium">Finances</span>
        </div>
        <a href="{% url 'salary_list' %}"
           class="flex items-center gap-2.5 px-3 py-2 rounded-card text-[13px] font-medium transition-colors duration-150
                  {% if 'salary' in request.resolver_match.url_name %}
                  bg-elevated text-zinc-100 border border-border-subtle
                  {% else %}
                  text-zinc-400 hover:text-zinc-200 hover:bg-hover
                  {% endif %}">
            <i data-lucide="wallet" class="w-4 h-4"></i>
            Salaries
        </a>
```

**Step 2: Register URL route (placeholder)**

In `config/urls.py`, add after line 22:
```python
    path('salaries/', include('apps.salaries.urls')),
```

**Step 3: Add placeholder view and URL**

Update `apps/salaries/urls.py`:
```python
from django.urls import path

from . import views

urlpatterns = [
    path('', views.salary_list, name='salary_list'),
]
```

Update `apps/salaries/views.py`:
```python
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
```

**Step 4: Create placeholder template**

Create `templates/salaries/salary_list.html`:
```html
{% extends "base.html" %}

{% block title %}Salaries - WebFTL CRM{% endblock %}

{% block content %}
<div class="space-y-4">
    <div class="flex items-center justify-between">
        <h1 class="text-lg font-semibold text-zinc-100">Salaries</h1>
    </div>
    <p class="text-zinc-400">Salary list will be implemented here.</p>
</div>
{% endblock %}
```

**Step 5: Verify the page loads**

Run: `python manage.py runserver`
Navigate to: http://localhost:8000/salaries/
Expected: Page loads with placeholder content, sidebar shows Finances category

**Step 6: Commit**

```bash
git add templates/components/sidebar.html templates/salaries/ config/urls.py apps/salaries/urls.py apps/salaries/views.py
git commit -m "feat(salaries): add Finances category to sidebar with Salaries link"
```

---

## Task 5: Implement Salary List Page

**Files:**
- Modify: `apps/salaries/views.py`
- Modify: `templates/salaries/salary_list.html`
- Create: `templates/salaries/partials/salary_row.html`
- Create: `apps/salaries/tests/test_views.py`

**Step 1: Write failing tests for salary list**

Create `apps/salaries/tests/test_views.py`:
```python
import pytest
from decimal import Decimal
from django.urls import reverse

from apps.salaries.models import EmployeeSalary, SalaryMonth, Payment


@pytest.fixture
def employee_salary(user):
    return EmployeeSalary.objects.create(
        user=user,
        base_salary=Decimal('5000.00'),
        currency='EUR'
    )


class TestSalaryListView:
    def test_salary_list_requires_login(self, client):
        """Test that salary list requires authentication."""
        response = client.get(reverse('salary_list'))
        assert response.status_code == 302
        assert '/accounts/login/' in response.url

    def test_salary_list_displays_employees(self, client_logged_in, employee_salary):
        """Test that salary list shows employee salaries."""
        response = client_logged_in.get(reverse('salary_list'))
        assert response.status_code == 200
        assert b'Test User' in response.content
        assert b'5000.00' in response.content or b'5,000.00' in response.content

    def test_salary_list_empty_state(self, client_logged_in):
        """Test empty state when no salaries configured."""
        response = client_logged_in.get(reverse('salary_list'))
        assert response.status_code == 200
        assert b'No salaries configured' in response.content or b'Configure salary' in response.content
```

**Step 2: Run tests to see them fail**

Run: `pytest apps/salaries/tests/test_views.py -v`
Expected: Some tests fail (templates not fully implemented)

**Step 3: Update salary list view**

Update `apps/salaries/views.py`:
```python
from django.contrib.auth.decorators import login_required
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
```

**Step 4: Update salary list template**

Replace `templates/salaries/salary_list.html`:
```html
{% extends "base.html" %}

{% block title %}Salaries - WebFTL CRM{% endblock %}

{% block content %}
<div class="space-y-4">
    <!-- Header -->
    <div class="flex items-center justify-between">
        <div>
            <h1 class="text-lg font-semibold text-zinc-100">Salaries</h1>
            <p class="text-sm text-zinc-500 mt-0.5">Manage employee salary payments</p>
        </div>
        <button hx-get="{% url 'salary_create' %}"
                hx-target="#slide-over"
                hx-swap="innerHTML"
                hx-on::after-request="document.getElementById('slide-over').classList.remove('hidden'); lucide.createIcons();"
                class="flex items-center gap-2 px-3 py-1.5 bg-accent text-white text-sm font-medium rounded-card hover:bg-accent-hover transition-colors">
            <i data-lucide="plus" class="w-4 h-4"></i>
            Add Employee
        </button>
    </div>

    <!-- Salary List -->
    {% if salary_data %}
    <div class="bg-elevated rounded-card border border-border-subtle overflow-hidden">
        <table class="w-full">
            <thead class="bg-panel border-b border-border-subtle">
                <tr class="text-left text-xs text-zinc-500 uppercase tracking-wider">
                    <th class="px-4 py-3 font-medium">Employee</th>
                    <th class="px-4 py-3 font-medium">Base Salary</th>
                    <th class="px-4 py-3 font-medium">Current Month Status</th>
                    <th class="px-4 py-3 font-medium w-10"></th>
                </tr>
            </thead>
            <tbody class="divide-y divide-border-subtle">
                {% for item in salary_data %}
                    {% include 'salaries/partials/salary_row.html' with item=item %}
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% else %}
    <div class="flex flex-col items-center justify-center py-16 text-zinc-500">
        <i data-lucide="wallet" class="w-12 h-12 mb-4 opacity-30"></i>
        <p class="text-sm mb-2">No salaries configured yet</p>
        <button hx-get="{% url 'salary_create' %}"
                hx-target="#slide-over"
                hx-swap="innerHTML"
                hx-on::after-request="document.getElementById('slide-over').classList.remove('hidden'); lucide.createIcons();"
                class="text-accent hover:text-accent-hover text-sm">
            Configure first employee salary
        </button>
    </div>
    {% endif %}
</div>
{% endblock %}
```

**Step 5: Create salary row partial**

Create `templates/salaries/partials/salary_row.html`:
```html
<tr class="hover:bg-hover transition-colors cursor-pointer"
    hx-get="{% url 'salary_detail' item.salary.id %}"
    hx-push-url="true"
    hx-target="main"
    hx-swap="innerHTML">
    <td class="px-4 py-3">
        <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-full bg-accent-muted flex items-center justify-center">
                <span class="text-accent text-xs font-semibold">{{ item.salary.user.name|slice:":1"|upper }}</span>
            </div>
            <div>
                <div class="text-sm font-medium text-zinc-100">{{ item.salary.user.name }}</div>
                <div class="text-xs text-zinc-500">{{ item.salary.user.email }}</div>
            </div>
        </div>
    </td>
    <td class="px-4 py-3">
        <span class="text-sm text-zinc-100">
            {% if item.salary.currency == 'EUR' %}€{% elif item.salary.currency == 'GBP' %}£{% else %}${% endif %}{{ item.salary.base_salary|floatformat:2 }}
        </span>
        <span class="text-xs text-zinc-500">/month</span>
    </td>
    <td class="px-4 py-3">
        {% if item.current_month %}
            {% with status=item.current_month.status %}
            <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium
                {% if status == 'unpaid' %}bg-red-500/10 text-red-400
                {% elif status == 'partial' %}bg-yellow-500/10 text-yellow-400
                {% elif status == 'paid' %}bg-green-500/10 text-green-400
                {% elif status == 'bonus' %}bg-purple-500/10 text-purple-400
                {% endif %}">
                {% if status == 'unpaid' %}<i data-lucide="circle" class="w-3 h-3"></i>Unpaid
                {% elif status == 'partial' %}<i data-lucide="circle-dot" class="w-3 h-3"></i>Partial
                {% elif status == 'paid' %}<i data-lucide="check-circle" class="w-3 h-3"></i>Paid
                {% elif status == 'bonus' %}<i data-lucide="gift" class="w-3 h-3"></i>Bonus
                {% endif %}
            </span>
            {% endwith %}
        {% else %}
            <span class="text-xs text-zinc-500">No entry</span>
        {% endif %}
    </td>
    <td class="px-4 py-3">
        <i data-lucide="chevron-right" class="w-4 h-4 text-zinc-600"></i>
    </td>
</tr>
```

**Step 6: Add placeholder URLs for create and detail**

Update `apps/salaries/urls.py`:
```python
from django.urls import path

from . import views

urlpatterns = [
    path('', views.salary_list, name='salary_list'),
    path('create/', views.salary_create, name='salary_create'),
    path('<int:pk>/', views.salary_detail, name='salary_detail'),
]
```

**Step 7: Add placeholder views**

Add to `apps/salaries/views.py`:
```python
from django.http import HttpResponse


@login_required
def salary_create(request):
    """Create salary configuration drawer - placeholder."""
    return HttpResponse('<div class="p-4 text-zinc-400">Create form coming soon</div>')


@login_required
def salary_detail(request, pk):
    """Employee salary detail page - placeholder."""
    return HttpResponse('<div class="p-4 text-zinc-400">Detail page coming soon</div>')
```

**Step 8: Run tests**

Run: `pytest apps/salaries/tests/test_views.py -v`
Expected: All tests PASS

**Step 9: Commit**

```bash
git add apps/salaries/ templates/salaries/
git commit -m "feat(salaries): implement salary list page with employee table"
```

---

## Task 6: Implement Add Employee Salary Drawer

**Files:**
- Modify: `apps/salaries/views.py`
- Modify: `apps/salaries/forms.py`
- Create: `templates/salaries/partials/create_salary_drawer.html`
- Modify: `apps/salaries/tests/test_views.py`

**Step 1: Add tests for salary creation**

Add to `apps/salaries/tests/test_views.py`:
```python
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        email='other@example.com',
        name='Other User',
        password='testpass123'
    )


class TestSalaryCreateView:
    def test_salary_create_get(self, client_logged_in):
        """Test GET returns the create drawer form."""
        response = client_logged_in.get(reverse('salary_create'))
        assert response.status_code == 200
        assert b'Add Employee Salary' in response.content

    def test_salary_create_post_success(self, client_logged_in, other_user):
        """Test POST creates a new salary configuration."""
        response = client_logged_in.post(reverse('salary_create'), {
            'user': other_user.id,
            'base_salary': '4500.00',
            'currency': 'EUR',
        })
        assert response.status_code == 200
        assert EmployeeSalary.objects.filter(user=other_user).exists()
        salary = EmployeeSalary.objects.get(user=other_user)
        assert salary.base_salary == Decimal('4500.00')
        assert salary.currency == 'EUR'

    def test_salary_create_excludes_users_with_salary(self, client_logged_in, employee_salary, other_user):
        """Test form only shows users without salary configuration."""
        response = client_logged_in.get(reverse('salary_create'))
        assert response.status_code == 200
        # employee_salary.user should not be in the form options
        assert b'Other User' in response.content
        # user (who has employee_salary) should not be in options
```

**Step 2: Run tests to see them fail**

Run: `pytest apps/salaries/tests/test_views.py::TestSalaryCreateView -v`
Expected: Tests fail

**Step 3: Create the form**

Update `apps/salaries/forms.py`:
```python
from django import forms
from django.contrib.auth import get_user_model

from .models import EmployeeSalary, SalaryMonth, Payment

User = get_user_model()

INPUT_CLASSES = 'w-full bg-elevated border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none'


class EmployeeSalaryForm(forms.ModelForm):
    class Meta:
        model = EmployeeSalary
        fields = ['user', 'base_salary', 'currency']
        widgets = {
            'user': forms.Select(attrs={'class': INPUT_CLASSES}),
            'base_salary': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': '0.00',
                'step': '0.01',
            }),
            'currency': forms.Select(attrs={'class': INPUT_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show users who don't have a salary configuration yet
        users_with_salary = EmployeeSalary.objects.values_list('user_id', flat=True)
        self.fields['user'].queryset = User.objects.exclude(id__in=users_with_salary)
        self.fields['user'].label = 'Employee'
```

**Step 4: Update the view**

Update `salary_create` in `apps/salaries/views.py`:
```python
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
```

**Step 5: Create the drawer template**

Create `templates/salaries/partials/create_salary_drawer.html`:
```html
<div class="flex flex-col h-full">
    <!-- Drawer header -->
    <div class="flex-shrink-0 px-4 py-3 border-b border-border-subtle bg-panel/80">
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
                <i data-lucide="user-plus" class="w-4 h-4 text-zinc-500"></i>
                <h2 class="text-sm font-medium text-zinc-100">Add Employee Salary</h2>
            </div>
            <button onclick="document.getElementById('slide-over').classList.add('hidden')"
                    class="p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-elevated rounded transition-colors">
                <i data-lucide="x" class="w-4 h-4"></i>
            </button>
        </div>
    </div>

    <!-- Form -->
    <form hx-post="{% url 'salary_create' %}"
          hx-target="#slide-over"
          hx-swap="innerHTML"
          class="flex-1 overflow-y-auto p-4">
        {% csrf_token %}

        <div class="space-y-4">
            <!-- Employee -->
            <div>
                <label class="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Employee</label>
                <select name="user"
                        required
                        class="w-full bg-elevated border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none">
                    <option value="">Select an employee</option>
                    {% for user_choice in form.user.field.queryset %}
                        <option value="{{ user_choice.id }}" {% if form.user.value == user_choice.id|stringformat:"s" %}selected{% endif %}>
                            {{ user_choice.name }} ({{ user_choice.email }})
                        </option>
                    {% endfor %}
                </select>
                {% if form.user.errors %}
                    <p class="mt-1 text-xs text-red-400">{{ form.user.errors.0 }}</p>
                {% endif %}
            </div>

            <!-- Base Salary -->
            <div>
                <label class="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Base Monthly Salary</label>
                <input type="number"
                       name="base_salary"
                       step="0.01"
                       min="0"
                       required
                       value="{{ form.base_salary.value|default:'' }}"
                       class="w-full bg-elevated border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none"
                       placeholder="0.00">
                {% if form.base_salary.errors %}
                    <p class="mt-1 text-xs text-red-400">{{ form.base_salary.errors.0 }}</p>
                {% endif %}
            </div>

            <!-- Currency -->
            <div>
                <label class="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Currency</label>
                <select name="currency"
                        required
                        class="w-full bg-elevated border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none">
                    {% for value, label in form.currency.field.choices %}
                        <option value="{{ value }}" {% if form.currency.value == value or value == 'EUR' and not form.currency.value %}selected{% endif %}>
                            {{ label }}
                        </option>
                    {% endfor %}
                </select>
                {% if form.currency.errors %}
                    <p class="mt-1 text-xs text-red-400">{{ form.currency.errors.0 }}</p>
                {% endif %}
            </div>
        </div>

        <div class="flex gap-3 mt-6 pt-4 border-t border-border-subtle">
            <button type="submit"
                    class="flex-1 bg-accent text-white px-4 py-2 rounded-card text-sm font-medium hover:bg-accent-hover transition-colors">
                Add Employee
            </button>
            <button type="button"
                    onclick="document.getElementById('slide-over').classList.add('hidden')"
                    class="px-4 py-2 text-zinc-400 hover:text-zinc-300 text-sm transition-colors">
                Cancel
            </button>
        </div>
    </form>
</div>

<script>
if (typeof lucide !== 'undefined') {
    lucide.createIcons();
}
</script>
```

**Step 6: Run tests**

Run: `pytest apps/salaries/tests/test_views.py -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add apps/salaries/ templates/salaries/
git commit -m "feat(salaries): add employee salary creation drawer"
```

---

## Task 7: Implement Salary Detail Page

**Files:**
- Modify: `apps/salaries/views.py`
- Create: `templates/salaries/salary_detail.html`
- Create: `templates/salaries/partials/month_item.html`
- Create: `templates/salaries/partials/payment_item.html`
- Modify: `apps/salaries/tests/test_views.py`

**Step 1: Add tests for salary detail**

Add to `apps/salaries/tests/test_views.py`:
```python
class TestSalaryDetailView:
    def test_salary_detail_requires_login(self, client, employee_salary):
        """Test that salary detail requires authentication."""
        response = client.get(reverse('salary_detail', args=[employee_salary.id]))
        assert response.status_code == 302

    def test_salary_detail_displays_info(self, client_logged_in, employee_salary):
        """Test salary detail shows employee info and base salary."""
        response = client_logged_in.get(reverse('salary_detail', args=[employee_salary.id]))
        assert response.status_code == 200
        assert b'Test User' in response.content
        assert b'5000' in response.content or b'5,000' in response.content

    def test_salary_detail_shows_months(self, client_logged_in, employee_salary):
        """Test salary detail shows month entries."""
        SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        response = client_logged_in.get(reverse('salary_detail', args=[employee_salary.id]))
        assert response.status_code == 200
        assert b'January 2025' in response.content

    def test_salary_detail_404_for_invalid(self, client_logged_in):
        """Test 404 for non-existent salary."""
        response = client_logged_in.get(reverse('salary_detail', args=[99999]))
        assert response.status_code == 404
```

**Step 2: Run tests to see them fail**

Run: `pytest apps/salaries/tests/test_views.py::TestSalaryDetailView -v`
Expected: Tests fail

**Step 3: Update the view**

Update `salary_detail` in `apps/salaries/views.py`:
```python
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
```

**Step 4: Create salary detail template**

Create `templates/salaries/salary_detail.html`:
```html
{% extends "base.html" %}

{% block title %}{{ salary.user.name }} - Salaries - WebFTL CRM{% endblock %}

{% block content %}
<div class="space-y-4">
    <!-- Back link -->
    <a href="{% url 'salary_list' %}"
       class="inline-flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-300 transition-colors">
        <i data-lucide="arrow-left" class="w-4 h-4"></i>
        Back to Salaries
    </a>

    <!-- Header -->
    <div class="flex items-start justify-between">
        <div class="flex items-center gap-4">
            <div class="w-12 h-12 rounded-full bg-accent-muted flex items-center justify-center">
                <span class="text-accent text-lg font-semibold">{{ salary.user.name|slice:":1"|upper }}</span>
            </div>
            <div>
                <h1 class="text-lg font-semibold text-zinc-100">{{ salary.user.name }}</h1>
                <p class="text-sm text-zinc-500">{{ salary.user.email }}</p>
            </div>
        </div>
        <div class="text-right">
            <div class="text-sm text-zinc-500">Base Salary</div>
            <div class="text-xl font-semibold text-zinc-100">
                {% if salary.currency == 'EUR' %}€{% elif salary.currency == 'GBP' %}£{% else %}${% endif %}{{ salary.base_salary|floatformat:2 }}
                <span class="text-sm text-zinc-500 font-normal">/month</span>
            </div>
        </div>
    </div>

    <!-- Actions -->
    <div class="flex items-center gap-2">
        <button hx-get="{% url 'payment_create' salary.id %}"
                hx-target="#slide-over"
                hx-swap="innerHTML"
                hx-on::after-request="document.getElementById('slide-over').classList.remove('hidden'); lucide.createIcons();"
                class="flex items-center gap-2 px-3 py-1.5 bg-accent text-white text-sm font-medium rounded-card hover:bg-accent-hover transition-colors">
            <i data-lucide="plus" class="w-4 h-4"></i>
            Record Payment
        </button>
        <button hx-get="{% url 'month_create' salary.id %}"
                hx-target="#slide-over"
                hx-swap="innerHTML"
                hx-on::after-request="document.getElementById('slide-over').classList.remove('hidden'); lucide.createIcons();"
                class="flex items-center gap-2 px-3 py-1.5 bg-elevated text-zinc-300 text-sm font-medium rounded-card border border-border-subtle hover:bg-hover transition-colors">
            <i data-lucide="calendar-plus" class="w-4 h-4"></i>
            Add Month
        </button>
    </div>

    <!-- Months List -->
    <div class="bg-elevated rounded-card border border-border-subtle overflow-hidden">
        {% if months %}
        <div class="divide-y divide-border-subtle" x-data="{ expandedMonth: null }">
            {% for month in months %}
                {% include 'salaries/partials/month_item.html' %}
            {% endfor %}
        </div>
        {% else %}
        <div class="flex flex-col items-center justify-center py-12 text-zinc-500">
            <i data-lucide="calendar" class="w-10 h-10 mb-3 opacity-30"></i>
            <p class="text-sm mb-2">No salary months recorded yet</p>
            <button hx-get="{% url 'month_create' salary.id %}"
                    hx-target="#slide-over"
                    hx-swap="innerHTML"
                    hx-on::after-request="document.getElementById('slide-over').classList.remove('hidden'); lucide.createIcons();"
                    class="text-accent hover:text-accent-hover text-sm">
                Add the first month
            </button>
        </div>
        {% endif %}
    </div>
</div>
{% endblock %}
```

**Step 5: Create month item partial**

Create `templates/salaries/partials/month_item.html`:
```html
{% load static %}

<div class="bg-elevated">
    <!-- Month Header (clickable to expand) -->
    <div class="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-hover transition-colors"
         @click="expandedMonth = expandedMonth === {{ month.id }} ? null : {{ month.id }}">
        <div class="flex items-center gap-4">
            <!-- Month/Year -->
            <div class="min-w-[140px]">
                <div class="text-sm font-medium text-zinc-100 flex items-center gap-2">
                    {{ month.MONTH_NAMES|slice:month.month|last }} {{ month.year }}
                    {% if month.year == current_year and month.month == current_month %}
                        <span class="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-accent/20 text-accent">Current</span>
                    {% endif %}
                </div>
                <div class="text-xs text-zinc-500">
                    Expected: {% if salary.currency == 'EUR' %}€{% elif salary.currency == 'GBP' %}£{% else %}${% endif %}{{ month.expected_amount|floatformat:2 }}
                </div>
            </div>

            <!-- Status Badge -->
            {% with status=month.status %}
            <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium
                {% if status == 'unpaid' %}bg-red-500/10 text-red-400
                {% elif status == 'partial' %}bg-yellow-500/10 text-yellow-400
                {% elif status == 'paid' %}bg-green-500/10 text-green-400
                {% elif status == 'bonus' %}bg-purple-500/10 text-purple-400
                {% endif %}">
                {% if status == 'unpaid' %}<i data-lucide="circle" class="w-3 h-3"></i>Unpaid
                {% elif status == 'partial' %}<i data-lucide="circle-dot" class="w-3 h-3"></i>Partial
                {% elif status == 'paid' %}<i data-lucide="check-circle" class="w-3 h-3"></i>Paid
                {% elif status == 'bonus' %}<i data-lucide="gift" class="w-3 h-3"></i>Bonus
                {% endif %}
            </span>
            {% endwith %}

            <!-- Payment Summary -->
            <div class="text-sm text-zinc-400">
                {% if month.total_paid > 0 %}
                    Paid: {% if salary.currency == 'EUR' %}€{% elif salary.currency == 'GBP' %}£{% else %}${% endif %}{{ month.total_paid|floatformat:2 }}
                    {% if month.remaining > 0 %}
                        <span class="text-yellow-400">({% if salary.currency == 'EUR' %}€{% elif salary.currency == 'GBP' %}£{% else %}${% endif %}{{ month.remaining|floatformat:2 }} remaining)</span>
                    {% endif %}
                    {% if month.bonus_amount > 0 %}
                        <span class="text-purple-400">({% if salary.currency == 'EUR' %}€{% elif salary.currency == 'GBP' %}£{% else %}${% endif %}{{ month.bonus_amount|floatformat:2 }} bonus)</span>
                    {% endif %}
                {% else %}
                    <span class="text-zinc-500">No payments</span>
                {% endif %}
            </div>
        </div>

        <div class="flex items-center gap-3">
            <span class="text-xs text-zinc-500">{{ month.payment_count }} payment{{ month.payment_count|pluralize }}</span>
            <i data-lucide="chevron-down" class="w-4 h-4 text-zinc-500 transition-transform"
               :class="{ 'rotate-180': expandedMonth === {{ month.id }} }"></i>
        </div>
    </div>

    <!-- Expanded Payment List -->
    <div x-show="expandedMonth === {{ month.id }}"
         x-collapse
         class="border-t border-border-subtle bg-panel/50">
        {% if month.payments.all %}
        <div class="divide-y divide-border-subtle">
            {% for payment in month.payments.all %}
                {% include 'salaries/partials/payment_item.html' %}
            {% endfor %}
        </div>
        {% else %}
        <div class="px-4 py-6 text-center text-zinc-500 text-sm">
            No payments recorded for this month
        </div>
        {% endif %}
    </div>
</div>
```

**Step 6: Create payment item partial**

Create `templates/salaries/partials/payment_item.html`:
```html
<div class="flex items-center justify-between px-4 py-2.5 pl-8">
    <div class="flex items-center gap-4">
        <div class="w-8 h-8 rounded bg-elevated flex items-center justify-center">
            {% if payment.payment_method == 'cash' %}
                <i data-lucide="banknote" class="w-4 h-4 text-green-400"></i>
            {% elif payment.payment_method == 'bank_transfer' %}
                <i data-lucide="building-2" class="w-4 h-4 text-blue-400"></i>
            {% elif payment.payment_method == 'check' %}
                <i data-lucide="file-text" class="w-4 h-4 text-orange-400"></i>
            {% else %}
                <i data-lucide="circle" class="w-4 h-4 text-zinc-400"></i>
            {% endif %}
        </div>
        <div>
            <div class="text-sm text-zinc-100">
                {% if salary.currency == 'EUR' %}€{% elif salary.currency == 'GBP' %}£{% else %}${% endif %}{{ payment.amount|floatformat:2 }}
            </div>
            <div class="text-xs text-zinc-500">
                {{ payment.get_payment_method_display }} &middot; {{ payment.payment_date|date:"d/m/Y" }}
            </div>
        </div>
    </div>
    {% if payment.notes %}
    <div class="text-xs text-zinc-500 max-w-[200px] truncate" title="{{ payment.notes }}">
        {{ payment.notes }}
    </div>
    {% endif %}
</div>
```

**Step 7: Add placeholder URLs for payment and month creation**

Update `apps/salaries/urls.py`:
```python
from django.urls import path

from . import views

urlpatterns = [
    path('', views.salary_list, name='salary_list'),
    path('create/', views.salary_create, name='salary_create'),
    path('<int:pk>/', views.salary_detail, name='salary_detail'),
    path('<int:pk>/months/create/', views.month_create, name='month_create'),
    path('<int:pk>/payments/create/', views.payment_create, name='payment_create'),
]
```

**Step 8: Add placeholder views**

Add to `apps/salaries/views.py`:
```python
@login_required
def month_create(request, pk):
    """Create month entry drawer - placeholder."""
    return HttpResponse('<div class="p-4 text-zinc-400">Add month form coming soon</div>')


@login_required
def payment_create(request, pk):
    """Record payment drawer - placeholder."""
    return HttpResponse('<div class="p-4 text-zinc-400">Record payment form coming soon</div>')
```

**Step 9: Run tests**

Run: `pytest apps/salaries/tests/test_views.py -v`
Expected: All tests PASS

**Step 10: Commit**

```bash
git add apps/salaries/ templates/salaries/
git commit -m "feat(salaries): implement salary detail page with month list"
```

---

## Task 8: Implement Add Month Drawer

**Files:**
- Modify: `apps/salaries/views.py`
- Modify: `apps/salaries/forms.py`
- Create: `templates/salaries/partials/create_month_drawer.html`
- Modify: `apps/salaries/tests/test_views.py`

**Step 1: Add tests**

Add to `apps/salaries/tests/test_views.py`:
```python
class TestMonthCreateView:
    def test_month_create_get(self, client_logged_in, employee_salary):
        """Test GET returns the month create drawer."""
        response = client_logged_in.get(reverse('month_create', args=[employee_salary.id]))
        assert response.status_code == 200
        assert b'Add Month' in response.content

    def test_month_create_post_success(self, client_logged_in, employee_salary):
        """Test POST creates a new month entry."""
        response = client_logged_in.post(reverse('month_create', args=[employee_salary.id]), {
            'year': 2025,
            'month': 2,
            'expected_amount': '5500.00',
        })
        assert response.status_code == 200
        assert SalaryMonth.objects.filter(
            employee_salary=employee_salary,
            year=2025,
            month=2
        ).exists()

    def test_month_create_prefills_base_salary(self, client_logged_in, employee_salary):
        """Test form pre-fills expected amount with base salary."""
        response = client_logged_in.get(reverse('month_create', args=[employee_salary.id]))
        assert response.status_code == 200
        assert b'5000' in response.content
```

**Step 2: Run tests to see them fail**

Run: `pytest apps/salaries/tests/test_views.py::TestMonthCreateView -v`
Expected: Tests fail

**Step 3: Add form**

Add to `apps/salaries/forms.py`:
```python
class SalaryMonthForm(forms.ModelForm):
    MONTH_CHOICES = [
        (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
        (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
        (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December'),
    ]

    month = forms.ChoiceField(choices=MONTH_CHOICES, widget=forms.Select(attrs={'class': INPUT_CLASSES}))

    class Meta:
        model = SalaryMonth
        fields = ['year', 'month', 'expected_amount']
        widgets = {
            'year': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'min': 2020,
                'max': 2100,
            }),
            'expected_amount': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'step': '0.01',
                'min': '0',
            }),
        }

    def __init__(self, *args, **kwargs):
        self.employee_salary = kwargs.pop('employee_salary', None)
        super().__init__(*args, **kwargs)
        if self.employee_salary and not self.instance.pk:
            self.fields['expected_amount'].initial = self.employee_salary.base_salary

    def clean(self):
        cleaned_data = super().clean()
        year = cleaned_data.get('year')
        month = cleaned_data.get('month')

        if year and month and self.employee_salary:
            if SalaryMonth.objects.filter(
                employee_salary=self.employee_salary,
                year=year,
                month=month
            ).exists():
                raise forms.ValidationError(f'A record for this month already exists.')

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.employee_salary:
            instance.employee_salary = self.employee_salary
        if commit:
            instance.save()
        return instance
```

**Step 4: Update the view**

Update `month_create` in `apps/salaries/views.py`:
```python
from .forms import EmployeeSalaryForm, SalaryMonthForm


@login_required
def month_create(request, pk):
    """Create a new month entry for an employee salary."""
    salary = get_object_or_404(EmployeeSalary, pk=pk)

    if request.method == 'POST':
        form = SalaryMonthForm(request.POST, employee_salary=salary)
        if form.is_valid():
            form.save()
            response = HttpResponse('')
            return _set_salary_triggers(response, close=True)
        return render(request, 'salaries/partials/create_month_drawer.html', {
            'form': form,
            'salary': salary,
        })

    now = timezone.now()
    form = SalaryMonthForm(employee_salary=salary, initial={
        'year': now.year,
        'month': now.month,
    })
    return render(request, 'salaries/partials/create_month_drawer.html', {
        'form': form,
        'salary': salary,
    })
```

**Step 5: Create the drawer template**

Create `templates/salaries/partials/create_month_drawer.html`:
```html
<div class="flex flex-col h-full">
    <!-- Drawer header -->
    <div class="flex-shrink-0 px-4 py-3 border-b border-border-subtle bg-panel/80">
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
                <i data-lucide="calendar-plus" class="w-4 h-4 text-zinc-500"></i>
                <h2 class="text-sm font-medium text-zinc-100">Add Month</h2>
            </div>
            <button onclick="document.getElementById('slide-over').classList.add('hidden')"
                    class="p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-elevated rounded transition-colors">
                <i data-lucide="x" class="w-4 h-4"></i>
            </button>
        </div>
    </div>

    <!-- Form -->
    <form hx-post="{% url 'month_create' salary.id %}"
          hx-target="#slide-over"
          hx-swap="innerHTML"
          class="flex-1 overflow-y-auto p-4">
        {% csrf_token %}

        <div class="space-y-4">
            <!-- Employee Info -->
            <div class="p-3 bg-panel rounded-card border border-border-subtle">
                <div class="text-xs text-zinc-500">Employee</div>
                <div class="text-sm text-zinc-100">{{ salary.user.name }}</div>
            </div>

            <!-- Year and Month -->
            <div class="grid grid-cols-2 gap-3">
                <div>
                    <label class="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Year</label>
                    <input type="number"
                           name="year"
                           required
                           min="2020"
                           max="2100"
                           value="{{ form.year.value }}"
                           class="w-full bg-elevated border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none">
                    {% if form.year.errors %}
                        <p class="mt-1 text-xs text-red-400">{{ form.year.errors.0 }}</p>
                    {% endif %}
                </div>
                <div>
                    <label class="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Month</label>
                    <select name="month"
                            required
                            class="w-full bg-elevated border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none">
                        {% for value, label in form.fields.month.choices %}
                            <option value="{{ value }}" {% if form.month.value|stringformat:"s" == value|stringformat:"s" %}selected{% endif %}>
                                {{ label }}
                            </option>
                        {% endfor %}
                    </select>
                    {% if form.month.errors %}
                        <p class="mt-1 text-xs text-red-400">{{ form.month.errors.0 }}</p>
                    {% endif %}
                </div>
            </div>

            <!-- Expected Amount -->
            <div>
                <label class="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Expected Amount</label>
                <input type="number"
                       name="expected_amount"
                       step="0.01"
                       min="0"
                       required
                       value="{{ form.expected_amount.value }}"
                       class="w-full bg-elevated border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none"
                       placeholder="0.00">
                <p class="mt-1 text-xs text-zinc-500">
                    Base salary: {% if salary.currency == 'EUR' %}€{% elif salary.currency == 'GBP' %}£{% else %}${% endif %}{{ salary.base_salary|floatformat:2 }}
                </p>
                {% if form.expected_amount.errors %}
                    <p class="mt-1 text-xs text-red-400">{{ form.expected_amount.errors.0 }}</p>
                {% endif %}
            </div>

            {% if form.non_field_errors %}
            <div class="p-3 bg-red-500/10 border border-red-500/20 rounded-card">
                <p class="text-sm text-red-400">{{ form.non_field_errors.0 }}</p>
            </div>
            {% endif %}
        </div>

        <div class="flex gap-3 mt-6 pt-4 border-t border-border-subtle">
            <button type="submit"
                    class="flex-1 bg-accent text-white px-4 py-2 rounded-card text-sm font-medium hover:bg-accent-hover transition-colors">
                Add Month
            </button>
            <button type="button"
                    onclick="document.getElementById('slide-over').classList.add('hidden')"
                    class="px-4 py-2 text-zinc-400 hover:text-zinc-300 text-sm transition-colors">
                Cancel
            </button>
        </div>
    </form>
</div>

<script>
if (typeof lucide !== 'undefined') {
    lucide.createIcons();
}
</script>
```

**Step 6: Run tests**

Run: `pytest apps/salaries/tests/test_views.py::TestMonthCreateView -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add apps/salaries/ templates/salaries/
git commit -m "feat(salaries): add month creation drawer"
```

---

## Task 9: Implement Record Payment Drawer

**Files:**
- Modify: `apps/salaries/views.py`
- Modify: `apps/salaries/forms.py`
- Create: `templates/salaries/partials/create_payment_drawer.html`
- Modify: `apps/salaries/tests/test_views.py`

**Step 1: Add tests**

Add to `apps/salaries/tests/test_views.py`:
```python
class TestPaymentCreateView:
    def test_payment_create_get(self, client_logged_in, employee_salary):
        """Test GET returns the payment create drawer."""
        SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        response = client_logged_in.get(reverse('payment_create', args=[employee_salary.id]))
        assert response.status_code == 200
        assert b'Record Payment' in response.content

    def test_payment_create_post_success(self, client_logged_in, employee_salary):
        """Test POST creates a new payment."""
        month = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        response = client_logged_in.post(reverse('payment_create', args=[employee_salary.id]), {
            'salary_month': month.id,
            'amount': '2500.00',
            'payment_date': '2025-01-15',
            'payment_method': 'bank_transfer',
            'notes': 'First payment',
        })
        assert response.status_code == 200
        assert Payment.objects.filter(salary_month=month).exists()
        payment = Payment.objects.get(salary_month=month)
        assert payment.amount == Decimal('2500.00')

    def test_payment_create_shows_existing_months(self, client_logged_in, employee_salary):
        """Test form shows existing months for selection."""
        SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=2,
            expected_amount=Decimal('5000.00')
        )
        response = client_logged_in.get(reverse('payment_create', args=[employee_salary.id]))
        assert response.status_code == 200
        assert b'January 2025' in response.content
        assert b'February 2025' in response.content
```

**Step 2: Run tests to see them fail**

Run: `pytest apps/salaries/tests/test_views.py::TestPaymentCreateView -v`
Expected: Tests fail

**Step 3: Add form**

Add to `apps/salaries/forms.py`:
```python
from datetime import date


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['salary_month', 'amount', 'payment_date', 'payment_method', 'notes']
        widgets = {
            'salary_month': forms.Select(attrs={'class': INPUT_CLASSES}),
            'amount': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'step': '0.01',
                'min': '0.01',
                'placeholder': '0.00',
            }),
            'payment_date': forms.DateInput(attrs={
                'class': INPUT_CLASSES,
                'type': 'date',
            }),
            'payment_method': forms.Select(attrs={'class': INPUT_CLASSES}),
            'notes': forms.Textarea(attrs={
                'class': INPUT_CLASSES,
                'rows': 2,
                'placeholder': 'Reference number, notes, etc.',
            }),
        }

    def __init__(self, *args, **kwargs):
        self.employee_salary = kwargs.pop('employee_salary', None)
        super().__init__(*args, **kwargs)

        if self.employee_salary:
            self.fields['salary_month'].queryset = self.employee_salary.months.all()
            self.fields['salary_month'].label_from_instance = lambda obj: f"{obj.MONTH_NAMES[obj.month]} {obj.year}"

        # Default to today
        self.fields['payment_date'].initial = date.today()
        self.fields['notes'].required = False
```

**Step 4: Update the view**

Update `payment_create` in `apps/salaries/views.py`:
```python
from .forms import EmployeeSalaryForm, SalaryMonthForm, PaymentForm


@login_required
def payment_create(request, pk):
    """Record a payment for an employee salary."""
    salary = get_object_or_404(EmployeeSalary, pk=pk)

    if request.method == 'POST':
        form = PaymentForm(request.POST, employee_salary=salary)
        if form.is_valid():
            form.save()
            response = HttpResponse('')
            return _set_salary_triggers(response, close=True)
        return render(request, 'salaries/partials/create_payment_drawer.html', {
            'form': form,
            'salary': salary,
        })

    form = PaymentForm(employee_salary=salary)
    return render(request, 'salaries/partials/create_payment_drawer.html', {
        'form': form,
        'salary': salary,
    })
```

**Step 5: Create the drawer template**

Create `templates/salaries/partials/create_payment_drawer.html`:
```html
<div class="flex flex-col h-full">
    <!-- Drawer header -->
    <div class="flex-shrink-0 px-4 py-3 border-b border-border-subtle bg-panel/80">
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
                <i data-lucide="banknote" class="w-4 h-4 text-zinc-500"></i>
                <h2 class="text-sm font-medium text-zinc-100">Record Payment</h2>
            </div>
            <button onclick="document.getElementById('slide-over').classList.add('hidden')"
                    class="p-1.5 text-zinc-500 hover:text-zinc-300 hover:bg-elevated rounded transition-colors">
                <i data-lucide="x" class="w-4 h-4"></i>
            </button>
        </div>
    </div>

    <!-- Form -->
    <form hx-post="{% url 'payment_create' salary.id %}"
          hx-target="#slide-over"
          hx-swap="innerHTML"
          class="flex-1 overflow-y-auto p-4">
        {% csrf_token %}

        <div class="space-y-4">
            <!-- Employee Info -->
            <div class="p-3 bg-panel rounded-card border border-border-subtle">
                <div class="text-xs text-zinc-500">Employee</div>
                <div class="text-sm text-zinc-100">{{ salary.user.name }}</div>
            </div>

            <!-- Month Selection -->
            <div>
                <label class="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Month</label>
                {% if form.salary_month.field.queryset.exists %}
                <select name="salary_month"
                        required
                        class="w-full bg-elevated border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none">
                    <option value="">Select a month</option>
                    {% for month in form.salary_month.field.queryset %}
                        <option value="{{ month.id }}" {% if form.salary_month.value == month.id|stringformat:"s" %}selected{% endif %}>
                            {{ month.MONTH_NAMES|slice:month.month|last }} {{ month.year }}
                            ({% if salary.currency == 'EUR' %}€{% elif salary.currency == 'GBP' %}£{% else %}${% endif %}{{ month.remaining|floatformat:2 }} remaining)
                        </option>
                    {% endfor %}
                </select>
                {% else %}
                <div class="p-3 bg-yellow-500/10 border border-yellow-500/20 rounded-card">
                    <p class="text-sm text-yellow-400">No months configured yet. Please add a month first.</p>
                </div>
                {% endif %}
                {% if form.salary_month.errors %}
                    <p class="mt-1 text-xs text-red-400">{{ form.salary_month.errors.0 }}</p>
                {% endif %}
            </div>

            <!-- Amount -->
            <div>
                <label class="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Amount</label>
                <input type="number"
                       name="amount"
                       step="0.01"
                       min="0.01"
                       required
                       value="{{ form.amount.value|default:'' }}"
                       class="w-full bg-elevated border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none"
                       placeholder="0.00">
                {% if form.amount.errors %}
                    <p class="mt-1 text-xs text-red-400">{{ form.amount.errors.0 }}</p>
                {% endif %}
            </div>

            <!-- Payment Date -->
            <div>
                <label class="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Payment Date</label>
                <input type="date"
                       name="payment_date"
                       required
                       value="{{ form.payment_date.value|date:'Y-m-d' }}"
                       class="w-full bg-elevated border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none">
                {% if form.payment_date.errors %}
                    <p class="mt-1 text-xs text-red-400">{{ form.payment_date.errors.0 }}</p>
                {% endif %}
            </div>

            <!-- Payment Method -->
            <div>
                <label class="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Payment Method</label>
                <select name="payment_method"
                        required
                        class="w-full bg-elevated border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none">
                    {% for value, label in form.fields.payment_method.choices %}
                        <option value="{{ value }}" {% if form.payment_method.value == value %}selected{% endif %}>
                            {{ label }}
                        </option>
                    {% endfor %}
                </select>
                {% if form.payment_method.errors %}
                    <p class="mt-1 text-xs text-red-400">{{ form.payment_method.errors.0 }}</p>
                {% endif %}
            </div>

            <!-- Notes -->
            <div>
                <label class="block text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Notes (optional)</label>
                <textarea name="notes"
                          rows="2"
                          class="w-full bg-elevated border border-border-subtle rounded-card px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none resize-none"
                          placeholder="Reference number, notes, etc.">{{ form.notes.value|default:'' }}</textarea>
                {% if form.notes.errors %}
                    <p class="mt-1 text-xs text-red-400">{{ form.notes.errors.0 }}</p>
                {% endif %}
            </div>
        </div>

        <div class="flex gap-3 mt-6 pt-4 border-t border-border-subtle">
            {% if form.salary_month.field.queryset.exists %}
            <button type="submit"
                    class="flex-1 bg-accent text-white px-4 py-2 rounded-card text-sm font-medium hover:bg-accent-hover transition-colors">
                Record Payment
            </button>
            {% else %}
            <button type="button"
                    hx-get="{% url 'month_create' salary.id %}"
                    hx-target="#slide-over"
                    hx-swap="innerHTML"
                    class="flex-1 bg-accent text-white px-4 py-2 rounded-card text-sm font-medium hover:bg-accent-hover transition-colors">
                Add Month First
            </button>
            {% endif %}
            <button type="button"
                    onclick="document.getElementById('slide-over').classList.add('hidden')"
                    class="px-4 py-2 text-zinc-400 hover:text-zinc-300 text-sm transition-colors">
                Cancel
            </button>
        </div>
    </form>
</div>

<script>
if (typeof lucide !== 'undefined') {
    lucide.createIcons();
}
</script>
```

**Step 6: Run tests**

Run: `pytest apps/salaries/tests/test_views.py::TestPaymentCreateView -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add apps/salaries/ templates/salaries/
git commit -m "feat(salaries): add payment recording drawer"
```

---

## Task 10: Add HTMX Refresh Triggers

**Files:**
- Modify: `templates/salaries/salary_list.html`
- Modify: `templates/salaries/salary_detail.html`

**Step 1: Update salary list to listen for refresh**

In `templates/salaries/salary_list.html`, add `hx-trigger` to the main content div:

Update the `{% if salary_data %}` block wrapper:
```html
    <!-- Salary List -->
    <div id="salary-list-content"
         hx-get="{% url 'salary_list' %}"
         hx-trigger="refreshSalaryList from:body"
         hx-select="#salary-list-content"
         hx-swap="outerHTML">
    {% if salary_data %}
    <!-- ... rest of content ... -->
    {% endif %}
    </div>
```

**Step 2: Update salary detail to listen for refresh**

In `templates/salaries/salary_detail.html`, wrap the months list in a refreshable div:

```html
    <!-- Months List -->
    <div id="months-list-content"
         hx-get="{% url 'salary_detail' salary.id %}"
         hx-trigger="refreshSalaryList from:body"
         hx-select="#months-list-content"
         hx-swap="outerHTML"
         class="bg-elevated rounded-card border border-border-subtle overflow-hidden">
        <!-- ... months content ... -->
    </div>
```

**Step 3: Test manually**

Run: `python manage.py runserver`
Test: Add a payment, verify the list refreshes automatically

**Step 4: Commit**

```bash
git add templates/salaries/
git commit -m "feat(salaries): add HTMX refresh triggers for real-time updates"
```

---

## Task 11: Run Full Test Suite and Fix Issues

**Files:**
- Various (depending on issues found)

**Step 1: Run all salaries tests**

Run: `pytest apps/salaries/ -v`
Expected: All tests PASS

**Step 2: Run full project test suite**

Run: `pytest --tb=short`
Expected: All tests PASS (no regressions)

**Step 3: Fix any issues found**

If tests fail, fix them one by one.

**Step 4: Commit any fixes**

```bash
git add .
git commit -m "fix(salaries): address test failures"
```

---

## Task 12: Final Manual Testing Checklist

**Verification steps (manual):**

1. Navigate to `/salaries/` - see empty state
2. Click "Add Employee" - drawer opens
3. Select user, enter salary, submit - employee appears in list
4. Click employee row - detail page loads
5. Click "Add Month" - drawer opens with current month pre-filled
6. Submit month - month appears in list
7. Click "Record Payment" - drawer opens
8. Submit payment - payment appears under month
9. Verify status badges update correctly (Unpaid → Partial → Paid → Bonus)
10. Verify "Finances" category appears in sidebar
11. Verify date format is DD/MM/YYYY throughout

**Step 1: Start dev server**

Run: `python manage.py runserver`

**Step 2: Complete manual testing**

Follow the checklist above.

**Step 3: Final commit if all looks good**

```bash
git add .
git commit -m "feat(salaries): complete salary management app implementation"
```

---

## Summary

This plan implements a complete Salaries app with:
- 3 models: EmployeeSalary, SalaryMonth, Payment
- List page showing all employees with current month status
- Detail page with expandable month list and payments
- HTMX drawers for creating salaries, months, and payments
- Automatic status calculation (unpaid/partial/paid/bonus)
- European date format (DD/MM/YYYY)
- Full test coverage
