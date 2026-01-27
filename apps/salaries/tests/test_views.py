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
