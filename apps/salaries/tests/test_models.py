import pytest
from decimal import Decimal
from datetime import date
from django.contrib.auth import get_user_model
from django.db import IntegrityError

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
def another_user(db):
    return User.objects.create_user(
        email='another@example.com',
        name='Another Employee',
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
        year=2025,
        month=1,
        expected_amount=Decimal('5000.00')
    )


@pytest.mark.django_db
class TestEmployeeSalaryModel:
    """Tests for the EmployeeSalary model."""

    def test_create_employee_salary(self, user):
        """Test creating an EmployeeSalary record."""
        salary = EmployeeSalary.objects.create(
            user=user,
            base_salary=Decimal('5000.00'),
            currency='EUR'
        )
        assert salary.pk is not None
        assert salary.user == user
        assert salary.base_salary == Decimal('5000.00')
        assert salary.currency == 'EUR'
        assert salary.created_at is not None
        assert salary.updated_at is not None

    def test_employee_salary_str(self, employee_salary):
        """Test the string representation."""
        expected = 'Test Employee - 5000.00 EUR'
        assert str(employee_salary) == expected

    def test_employee_salary_unique_constraint(self, user, employee_salary):
        """Test that a user can only have one salary configuration."""
        with pytest.raises(IntegrityError):
            EmployeeSalary.objects.create(
                user=user,
                base_salary=Decimal('6000.00'),
                currency='USD'
            )

    def test_currency_choices(self, user):
        """Test that currency choices are validated."""
        # Test valid currencies
        for currency in ['USD', 'EUR', 'GBP']:
            # Clean up any existing salary
            EmployeeSalary.objects.filter(user=user).delete()
            salary = EmployeeSalary.objects.create(
                user=user,
                base_salary=Decimal('5000.00'),
                currency=currency
            )
            assert salary.currency == currency

    def test_default_currency(self, user):
        """Test that default currency is EUR."""
        salary = EmployeeSalary.objects.create(
            user=user,
            base_salary=Decimal('5000.00')
        )
        assert salary.currency == 'EUR'

    def test_related_name_salary_config(self, employee_salary):
        """Test that user.salary_config works."""
        user = employee_salary.user
        assert user.salary_config == employee_salary

    def test_cascade_delete(self, employee_salary):
        """Test that deleting user deletes salary config."""
        user = employee_salary.user
        salary_id = employee_salary.pk
        user.delete()
        assert not EmployeeSalary.objects.filter(pk=salary_id).exists()


@pytest.mark.django_db
class TestSalaryMonthModel:
    """Tests for the SalaryMonth model."""

    def test_create_salary_month(self, employee_salary):
        """Test creating a SalaryMonth record."""
        month = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        assert month.pk is not None
        assert month.employee_salary == employee_salary
        assert month.year == 2025
        assert month.month == 1
        assert month.expected_amount == Decimal('5000.00')
        assert month.created_at is not None

    def test_salary_month_str(self, salary_month):
        """Test the string representation."""
        expected = 'Test Employee - January 2025'
        assert str(salary_month) == expected

    def test_unique_year_month_constraint(self, employee_salary, salary_month):
        """Test that employee can only have one record per month/year."""
        with pytest.raises(IntegrityError):
            SalaryMonth.objects.create(
                employee_salary=employee_salary,
                year=2025,
                month=1,
                expected_amount=Decimal('5500.00')
            )

    def test_same_month_different_employees(self, employee_salary, another_user):
        """Test that different employees can have same month/year."""
        another_salary = EmployeeSalary.objects.create(
            user=another_user,
            base_salary=Decimal('6000.00'),
            currency='USD'
        )
        # First employee already has January 2025 from salary_month fixture
        SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        # Second employee should also be able to have January 2025
        month = SalaryMonth.objects.create(
            employee_salary=another_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('6000.00')
        )
        assert month.pk is not None

    def test_total_paid_no_payments(self, salary_month):
        """Test total_paid property with no payments."""
        assert salary_month.total_paid == Decimal('0')

    def test_total_paid_with_payments(self, salary_month):
        """Test total_paid property sums all payments."""
        Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('2000.00'),
            payment_date=date(2025, 1, 15),
            payment_method='bank_transfer'
        )
        Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('1500.00'),
            payment_date=date(2025, 1, 20),
            payment_method='cash'
        )
        assert salary_month.total_paid == Decimal('3500.00')

    def test_remaining_full_amount(self, salary_month):
        """Test remaining property when nothing paid."""
        assert salary_month.remaining == Decimal('5000.00')

    def test_remaining_partial_payment(self, salary_month):
        """Test remaining property with partial payment."""
        Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('2000.00'),
            payment_date=date(2025, 1, 15),
            payment_method='bank_transfer'
        )
        assert salary_month.remaining == Decimal('3000.00')

    def test_remaining_fully_paid(self, salary_month):
        """Test remaining property when fully paid."""
        Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('5000.00'),
            payment_date=date(2025, 1, 15),
            payment_method='bank_transfer'
        )
        assert salary_month.remaining == Decimal('0')

    def test_remaining_overpaid(self, salary_month):
        """Test remaining property when overpaid (should be 0)."""
        Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('6000.00'),
            payment_date=date(2025, 1, 15),
            payment_method='bank_transfer'
        )
        assert salary_month.remaining == Decimal('0')

    def test_bonus_amount_no_bonus(self, salary_month):
        """Test bonus_amount property when not overpaid."""
        Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('4000.00'),
            payment_date=date(2025, 1, 15),
            payment_method='bank_transfer'
        )
        assert salary_month.bonus_amount == Decimal('0')

    def test_bonus_amount_exactly_paid(self, salary_month):
        """Test bonus_amount property when exactly paid."""
        Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('5000.00'),
            payment_date=date(2025, 1, 15),
            payment_method='bank_transfer'
        )
        assert salary_month.bonus_amount == Decimal('0')

    def test_bonus_amount_overpaid(self, salary_month):
        """Test bonus_amount property when overpaid."""
        Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('6500.00'),
            payment_date=date(2025, 1, 15),
            payment_method='bank_transfer'
        )
        assert salary_month.bonus_amount == Decimal('1500.00')

    def test_status_unpaid(self, salary_month):
        """Test status property when unpaid."""
        assert salary_month.status == 'unpaid'

    def test_status_partial(self, salary_month):
        """Test status property when partially paid."""
        Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('2500.00'),
            payment_date=date(2025, 1, 15),
            payment_method='bank_transfer'
        )
        assert salary_month.status == 'partial'

    def test_status_paid(self, salary_month):
        """Test status property when fully paid."""
        Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('5000.00'),
            payment_date=date(2025, 1, 15),
            payment_method='bank_transfer'
        )
        assert salary_month.status == 'paid'

    def test_status_bonus(self, salary_month):
        """Test status property when overpaid (bonus)."""
        Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('5500.00'),
            payment_date=date(2025, 1, 15),
            payment_method='bank_transfer'
        )
        assert salary_month.status == 'bonus'

    def test_payment_count_zero(self, salary_month):
        """Test payment_count property with no payments."""
        assert salary_month.payment_count == 0

    def test_payment_count_multiple(self, salary_month):
        """Test payment_count property with multiple payments."""
        Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('1000.00'),
            payment_date=date(2025, 1, 10),
            payment_method='cash'
        )
        Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('2000.00'),
            payment_date=date(2025, 1, 15),
            payment_method='bank_transfer'
        )
        Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('2000.00'),
            payment_date=date(2025, 1, 20),
            payment_method='check'
        )
        assert salary_month.payment_count == 3

    def test_ordering(self, employee_salary):
        """Test that months are ordered by year and month descending."""
        month1 = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2024,
            month=12,
            expected_amount=Decimal('5000.00')
        )
        month2 = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        month3 = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=2,
            expected_amount=Decimal('5000.00')
        )
        months = list(SalaryMonth.objects.filter(employee_salary=employee_salary))
        assert months[0] == month3  # 2025-02
        assert months[1] == month2  # 2025-01
        assert months[2] == month1  # 2024-12


@pytest.mark.django_db
class TestPaymentModel:
    """Tests for the Payment model."""

    def test_create_payment(self, salary_month):
        """Test creating a Payment record."""
        payment = Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('2500.00'),
            payment_date=date(2025, 1, 15),
            payment_method='bank_transfer',
            notes='First payment'
        )
        assert payment.pk is not None
        assert payment.salary_month == salary_month
        assert payment.amount == Decimal('2500.00')
        assert payment.payment_date == date(2025, 1, 15)
        assert payment.payment_method == 'bank_transfer'
        assert payment.notes == 'First payment'
        assert payment.created_at is not None

    def test_payment_str(self, salary_month):
        """Test the string representation."""
        payment = Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('2500.00'),
            payment_date=date(2025, 1, 15),
            payment_method='bank_transfer'
        )
        expected = '2500.00 on 15/01/2025'
        assert str(payment) == expected

    def test_payment_method_choices(self, salary_month):
        """Test that payment method choices are valid."""
        methods = ['cash', 'bank_transfer', 'check', 'other']
        for method in methods:
            payment = Payment.objects.create(
                salary_month=salary_month,
                amount=Decimal('1000.00'),
                payment_date=date(2025, 1, 15),
                payment_method=method
            )
            assert payment.payment_method == method

    def test_notes_blank(self, salary_month):
        """Test that notes can be blank."""
        payment = Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('2500.00'),
            payment_date=date(2025, 1, 15),
            payment_method='cash'
        )
        assert payment.notes == ''

    def test_related_name_payments(self, salary_month):
        """Test that salary_month.payments works."""
        Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('2500.00'),
            payment_date=date(2025, 1, 15),
            payment_method='bank_transfer'
        )
        assert salary_month.payments.count() == 1

    def test_cascade_delete_salary_month(self, salary_month):
        """Test that deleting salary_month deletes payments."""
        payment = Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('2500.00'),
            payment_date=date(2025, 1, 15),
            payment_method='bank_transfer'
        )
        payment_id = payment.pk
        salary_month.delete()
        assert not Payment.objects.filter(pk=payment_id).exists()

    def test_ordering(self, salary_month):
        """Test that payments are ordered by payment_date descending."""
        p1 = Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('1000.00'),
            payment_date=date(2025, 1, 10),
            payment_method='cash'
        )
        p2 = Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('2000.00'),
            payment_date=date(2025, 1, 20),
            payment_method='bank_transfer'
        )
        p3 = Payment.objects.create(
            salary_month=salary_month,
            amount=Decimal('1500.00'),
            payment_date=date(2025, 1, 15),
            payment_method='check'
        )
        payments = list(salary_month.payments.all())
        assert payments[0] == p2  # Jan 20
        assert payments[1] == p3  # Jan 15
        assert payments[2] == p1  # Jan 10
