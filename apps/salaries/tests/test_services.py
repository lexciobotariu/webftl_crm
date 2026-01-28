# apps/salaries/tests/test_services.py
"""Tests for the salaries service layer."""
import pytest
from decimal import Decimal
from datetime import date

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.salaries import services
from apps.salaries.forms import EmployeeSalaryForm, SalaryMonthForm, PaymentForm
from apps.salaries.models import EmployeeSalary, SalaryMonth, Payment

User = get_user_model()


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def user(db):
    """Create a non-staff employee user."""
    return User.objects.create_user(
        email='employee@example.com',
        name='Test Employee',
        password='testpass123',
        is_staff=False
    )


@pytest.fixture
def admin_user(db):
    """Create a staff/admin user."""
    return User.objects.create_user(
        email='admin@example.com',
        name='Admin User',
        password='testpass123',
        is_staff=True
    )


@pytest.fixture
def another_user(db):
    """Create another non-staff user for testing availability."""
    return User.objects.create_user(
        email='another@example.com',
        name='Another Employee',
        password='testpass123',
        is_staff=False
    )


@pytest.fixture
def employee_salary(user):
    """Create an employee salary configuration."""
    return EmployeeSalary.objects.create(
        user=user,
        base_salary=Decimal('5000.00'),
        currency='EUR'
    )


@pytest.fixture
def salary_month(employee_salary):
    """Create a salary month entry."""
    return SalaryMonth.objects.create(
        employee_salary=employee_salary,
        year=2025,
        month=1,
        expected_amount=Decimal('5000.00')
    )


@pytest.fixture
def payment(salary_month):
    """Create a payment."""
    return Payment.objects.create(
        salary_month=salary_month,
        amount=Decimal('2500.00'),
        payment_date=date(2025, 1, 15),
        payment_method='bank_transfer',
        notes='Test payment'
    )


# =============================================================================
# TestGetSalaryListData
# =============================================================================

@pytest.mark.django_db
class TestGetSalaryListData:
    """Tests for get_salary_list_data service function."""

    def test_returns_salary_data(self, employee_salary):
        """Test that salary data is returned correctly."""
        salary_data, current_year, current_month, has_available_users, has_any_users = (
            services.get_salary_list_data()
        )

        assert len(salary_data) == 1
        assert salary_data[0]['salary'] == employee_salary
        assert current_year == timezone.now().year
        assert current_month == timezone.now().month

    def test_returns_current_month_entry(self, employee_salary):
        """Test that current month entry is included if it exists."""
        now = timezone.now()
        current_month_entry = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=now.year,
            month=now.month,
            expected_amount=Decimal('5000.00')
        )

        salary_data, _, _, _, _ = services.get_salary_list_data()

        assert salary_data[0]['current_month'] == current_month_entry

    def test_has_available_users_true(self, employee_salary, another_user):
        """Test has_available_users is True when a non-staff user without salary exists."""
        # employee_salary uses 'user', but 'another_user' has no salary config
        _, _, _, has_available_users, has_any_users = services.get_salary_list_data()

        assert has_available_users is True
        assert has_any_users is True

    def test_has_available_users_false(self, user):
        """Test has_available_users is False when all non-staff users have salaries."""
        # Create salary for the only non-staff user
        EmployeeSalary.objects.create(
            user=user,
            base_salary=Decimal('5000.00'),
            currency='EUR'
        )

        _, _, _, has_available_users, has_any_users = services.get_salary_list_data()

        assert has_available_users is False
        assert has_any_users is True

    def test_excludes_staff_from_available_users(self, admin_user):
        """Test that staff users are excluded from available users count."""
        # Only admin_user exists, and they are staff
        _, _, _, has_available_users, has_any_users = services.get_salary_list_data()

        # Admin (staff) user should not be counted as available employee
        assert has_available_users is False
        assert has_any_users is False  # No non-staff users exist


# =============================================================================
# TestEmployeeSalaryServices
# =============================================================================

@pytest.mark.django_db
class TestEmployeeSalaryServices:
    """Tests for employee salary CRUD service functions."""

    def test_create_employee_salary(self, user):
        """Test creating an employee salary via service."""
        form_data = {
            'user': user.pk,
            'base_salary': '6000.00',
            'currency': 'USD',
        }
        form = EmployeeSalaryForm(data=form_data)
        assert form.is_valid(), form.errors

        salary = services.create_employee_salary(form)

        assert salary.pk is not None
        assert salary.user == user
        assert salary.base_salary == Decimal('6000.00')
        assert salary.currency == 'USD'

    def test_update_employee_salary(self, employee_salary, another_user):
        """Test updating an employee salary via service."""
        # Note: EmployeeSalaryForm excludes users who already have salaries from the
        # user queryset. For this test, we assign to another_user who doesn't have
        # a salary config yet. In production, editing typically only changes
        # base_salary/currency, not the user.
        form_data = {
            'user': another_user.pk,
            'base_salary': '7500.00',
            'currency': 'GBP',
        }
        form = EmployeeSalaryForm(data=form_data, instance=employee_salary)
        assert form.is_valid(), form.errors

        updated_salary = services.update_employee_salary(form)

        updated_salary.refresh_from_db()
        assert updated_salary.user == another_user
        assert updated_salary.base_salary == Decimal('7500.00')
        assert updated_salary.currency == 'GBP'

    def test_delete_employee_salary(self, employee_salary):
        """Test deleting an employee salary via service."""
        salary_pk = employee_salary.pk

        services.delete_employee_salary(employee_salary)

        assert not EmployeeSalary.objects.filter(pk=salary_pk).exists()


# =============================================================================
# TestSalaryMonthServices
# =============================================================================

@pytest.mark.django_db
class TestSalaryMonthServices:
    """Tests for salary month CRUD service functions."""

    def test_get_salary_detail_data(self, employee_salary, salary_month, payment):
        """Test get_salary_detail_data returns correct data."""
        salary, months, current_year, current_month = services.get_salary_detail_data(
            employee_salary.pk
        )

        assert salary == employee_salary
        assert salary_month in months
        assert current_year == timezone.now().year
        assert current_month == timezone.now().month

    def test_create_salary_month(self, employee_salary):
        """Test creating a salary month via service."""
        form_data = {
            'year': 2025,
            'month': 6,
            'expected_amount': '5500.00',
        }
        form = SalaryMonthForm(data=form_data, employee_salary=employee_salary)
        assert form.is_valid(), form.errors

        month = services.create_salary_month(form)

        assert month.pk is not None
        assert month.employee_salary == employee_salary
        assert month.year == 2025
        assert month.month == 6
        assert month.expected_amount == Decimal('5500.00')

    def test_update_salary_month(self, salary_month):
        """Test updating a salary month via service."""
        form_data = {
            'year': 2025,
            'month': 1,
            'expected_amount': '5200.00',
        }
        form = SalaryMonthForm(
            data=form_data,
            instance=salary_month,
            employee_salary=salary_month.employee_salary
        )
        assert form.is_valid(), form.errors

        updated_month = services.update_salary_month(form)

        updated_month.refresh_from_db()
        assert updated_month.expected_amount == Decimal('5200.00')

    def test_delete_salary_month(self, salary_month):
        """Test deleting a salary month via service."""
        month_pk = salary_month.pk

        services.delete_salary_month(salary_month)

        assert not SalaryMonth.objects.filter(pk=month_pk).exists()


# =============================================================================
# TestPaymentServices
# =============================================================================

@pytest.mark.django_db
class TestPaymentServices:
    """Tests for payment CRUD service functions."""

    def test_create_payment(self, salary_month):
        """Test creating a payment via service."""
        form_data = {
            'salary_month': salary_month.pk,
            'amount': '1500.00',
            'payment_date': '2025-01-20',
            'payment_method': 'cash',
            'notes': 'Cash payment',
        }
        form = PaymentForm(
            data=form_data,
            employee_salary=salary_month.employee_salary
        )
        assert form.is_valid(), form.errors

        payment = services.create_payment(form)

        assert payment.pk is not None
        assert payment.salary_month == salary_month
        assert payment.amount == Decimal('1500.00')
        assert payment.payment_date == date(2025, 1, 20)
        assert payment.payment_method == 'cash'
        assert payment.notes == 'Cash payment'

    def test_update_payment(self, payment):
        """Test updating a payment via service."""
        form_data = {
            'salary_month': payment.salary_month.pk,
            'amount': '3000.00',
            'payment_date': '2025-01-18',
            'payment_method': 'check',
            'notes': 'Updated payment',
        }
        form = PaymentForm(
            data=form_data,
            instance=payment,
            employee_salary=payment.salary_month.employee_salary
        )
        assert form.is_valid(), form.errors

        updated_payment = services.update_payment(form)

        updated_payment.refresh_from_db()
        assert updated_payment.amount == Decimal('3000.00')
        assert updated_payment.payment_date == date(2025, 1, 18)
        assert updated_payment.payment_method == 'check'
        assert updated_payment.notes == 'Updated payment'

    def test_delete_payment(self, payment):
        """Test deleting a payment via service."""
        payment_pk = payment.pk

        services.delete_payment(payment)

        assert not Payment.objects.filter(pk=payment_pk).exists()
