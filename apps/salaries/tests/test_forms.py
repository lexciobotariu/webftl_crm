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
