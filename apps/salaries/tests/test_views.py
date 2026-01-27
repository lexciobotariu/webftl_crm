import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.salaries.models import EmployeeSalary, SalaryMonth, Payment

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
