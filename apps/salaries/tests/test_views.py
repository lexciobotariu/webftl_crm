from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.salaries.models import EmployeeSalary, Payment, SalaryMonth

User = get_user_model()


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


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        email='other@example.com',
        name='Other User',
        password='testpass123'
    )


class TestSalaryCreateView:
    def test_salary_create_get(self, admin_client_logged_in):
        """Test GET returns the create drawer form."""
        response = admin_client_logged_in.get(reverse('salary_create'))
        assert response.status_code == 200
        assert b'Add Employee Salary' in response.content

    def test_salary_create_post_success(self, admin_client_logged_in, other_user):
        """Test POST creates a new salary configuration."""
        response = admin_client_logged_in.post(reverse('salary_create'), {
            'user': other_user.id,
            'base_salary': '4500.00',
            'currency': 'EUR',
        })
        assert response.status_code == 200
        assert EmployeeSalary.objects.filter(user=other_user).exists()
        salary = EmployeeSalary.objects.get(user=other_user)
        assert salary.base_salary == Decimal('4500.00')
        assert salary.currency == 'EUR'

    def test_salary_create_excludes_users_with_salary(self, admin_client_logged_in, employee_salary, other_user):
        """Test form only shows users without salary configuration."""
        response = admin_client_logged_in.get(reverse('salary_create'))
        assert response.status_code == 200
        # employee_salary.user should not be in the form options
        assert b'Other User' in response.content
        # user (who has employee_salary) should not be in options


class TestMonthCreateView:
    def test_month_create_get(self, admin_client_logged_in, employee_salary):
        """Test GET returns the month create drawer."""
        response = admin_client_logged_in.get(reverse('month_create', args=[employee_salary.id]))
        assert response.status_code == 200
        assert b'Add Month' in response.content

    def test_month_create_post_success(self, admin_client_logged_in, employee_salary):
        """Test POST creates a new month entry."""
        response = admin_client_logged_in.post(reverse('month_create', args=[employee_salary.id]), {
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

    def test_month_create_prefills_base_salary(self, admin_client_logged_in, employee_salary):
        """Test form pre-fills expected amount with base salary."""
        response = admin_client_logged_in.get(reverse('month_create', args=[employee_salary.id]))
        assert response.status_code == 200
        assert b'5000' in response.content

    def test_month_create_duplicate_validation(self, admin_client_logged_in, employee_salary):
        """Test validation prevents duplicate year/month for same employee."""
        # Create existing month entry
        SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=3,
            expected_amount=Decimal('5000.00')
        )
        # Try to create duplicate
        response = admin_client_logged_in.post(reverse('month_create', args=[employee_salary.id]), {
            'year': 2025,
            'month': 3,
            'expected_amount': '5500.00',
        })
        assert response.status_code == 200
        # Should show error, not create duplicate
        assert SalaryMonth.objects.filter(
            employee_salary=employee_salary,
            year=2025,
            month=3
        ).count() == 1
        assert b'already exists' in response.content


class TestPaymentCreateView:
    def test_payment_create_get(self, admin_client_logged_in, employee_salary):
        """Test GET returns the payment create drawer."""
        SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        response = admin_client_logged_in.get(reverse('payment_create', args=[employee_salary.id]))
        assert response.status_code == 200
        assert b'Record Payment' in response.content

    def test_payment_create_post_success(self, admin_client_logged_in, employee_salary):
        """Test POST creates a new payment."""
        month = SalaryMonth.objects.create(
            employee_salary=employee_salary,
            year=2025,
            month=1,
            expected_amount=Decimal('5000.00')
        )
        response = admin_client_logged_in.post(reverse('payment_create', args=[employee_salary.id]), {
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

    def test_payment_create_shows_existing_months(self, admin_client_logged_in, employee_salary):
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
        response = admin_client_logged_in.get(reverse('payment_create', args=[employee_salary.id]))
        assert response.status_code == 200
        assert b'January 2025' in response.content
        assert b'February 2025' in response.content
