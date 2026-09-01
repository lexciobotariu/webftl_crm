"""Boundary tests for the salaries section.

Reading salary data needs ``access_salaries``; every mutating view additionally
needs the admin role. These tests pin both halves of that contract so a future
change to the fixtures cannot silently erase the member-level coverage.
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.salaries.models import EmployeeSalary, Payment, SalaryMonth


@pytest.fixture
def employee_salary(user):
    return EmployeeSalary.objects.create(
        user=user, base_salary=Decimal('5000.00'), currency='EUR'
    )


@pytest.fixture
def salary_month(employee_salary):
    return SalaryMonth.objects.create(
        employee_salary=employee_salary,
        year=2025,
        month=1,
        expected_amount=Decimal('5000.00'),
    )


@pytest.fixture
def payment(salary_month):
    return Payment.objects.create(
        salary_month=salary_month, amount=Decimal('1000.00'), payment_date='2025-01-15'
    )


class TestMemberWithSalariesAccess:
    """A member holding ``access_salaries`` can read but not write."""

    def test_can_view_salary_list(self, client_logged_in, employee_salary):
        response = client_logged_in.get(reverse('salary_list'))
        assert response.status_code == 200

    def test_can_view_salary_detail(self, client_logged_in, employee_salary):
        response = client_logged_in.get(reverse('salary_detail', args=[employee_salary.pk]))
        assert response.status_code == 200

    @pytest.mark.parametrize('method', ['get', 'post'])
    def test_write_views_are_forbidden(
        self, method, client_logged_in, employee_salary, salary_month, payment
    ):
        forbidden_urls = [
            reverse('salary_create'),
            reverse('salary_edit', args=[employee_salary.pk]),
            reverse('salary_delete', args=[employee_salary.pk]),
            reverse('month_create', args=[employee_salary.pk]),
            reverse('month_edit', args=[employee_salary.pk, salary_month.pk]),
            reverse('month_delete', args=[employee_salary.pk, salary_month.pk]),
            reverse('payment_create', args=[employee_salary.pk]),
            reverse('payment_edit', args=[employee_salary.pk, payment.pk]),
            reverse('payment_delete', args=[employee_salary.pk, payment.pk]),
        ]
        for url in forbidden_urls:
            response = getattr(client_logged_in, method)(url, {})
            assert response.status_code in (403, 405), f'{method.upper()} {url} -> {response.status_code}'


class TestMemberWithoutSalariesAccess:
    def test_salary_list_is_forbidden(self, client, user, salaries_preset):
        salaries_preset.access_salaries = False
        salaries_preset.save(update_fields=['access_salaries'])
        client.force_login(user)
        response = client.get(reverse('salary_list'))
        assert response.status_code == 403


class TestAdminAccess:
    def test_admin_can_open_create_form(self, admin_client_logged_in):
        response = admin_client_logged_in.get(reverse('salary_create'))
        assert response.status_code == 200
