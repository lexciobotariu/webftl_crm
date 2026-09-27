"""Boundary tests for the salaries section.

``access_salaries`` opens the section and shows this person's rows.
``salaries_view_all`` shows every employee. ``salaries_edit`` creates and
changes salaries, months, and payments. Delete stays the admin role.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.accounts.permissions import PermissionPreset
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


def _other_employee(email, name):
    User = get_user_model()
    return User.objects.create_user(email=email, name=name, password='testpass123')


def _salary(employee, amount='5000.00'):
    return EmployeeSalary.objects.create(
        user=employee, base_salary=Decimal(amount), currency='EUR'
    )


class TestViewOwn:
    def test_list_and_detail_show_only_this_person(self, client_logged_in, user):
        own = _salary(user, '5000.00')
        hidden = _salary(_other_employee('hidden-pay@example.com', 'Hidden Pay'), '9000.00')

        listed = client_logged_in.get(reverse('salary_list'))
        assert listed.status_code == 200
        assert b'Test User' in listed.content
        assert b'Hidden Pay' not in listed.content
        assert b'9000' not in listed.content

        own_page = client_logged_in.get(reverse('salary_detail', args=[own.pk]))
        assert own_page.status_code == 200
        assert b'Test User' in own_page.content
        assert b'Add Month' not in own_page.content
        assert b'Record Payment' not in own_page.content

        assert client_logged_in.get(reverse('salary_detail', args=[hidden.pk])).status_code == 404


class TestViewAll:
    def test_every_salary_opens_and_edit_stays_forbidden(
        self, client_logged_in, user, salaries_preset
    ):
        salaries_preset.salaries_view_all = True
        salaries_preset.save(update_fields=['salaries_view_all'])
        own = _salary(user, '5000.00')
        other = _salary(_other_employee('viewall-other@example.com', 'View All Other'), '3000.00')

        listed = client_logged_in.get(reverse('salary_list'))
        assert listed.status_code == 200
        assert b'Test User' in listed.content
        assert b'View All Other' in listed.content
        assert b'Add Employee' not in listed.content

        assert client_logged_in.get(reverse('salary_detail', args=[own.pk])).status_code == 200
        other_page = client_logged_in.get(reverse('salary_detail', args=[other.pk]))
        assert other_page.status_code == 200
        assert b'Add Month' not in other_page.content
        assert b'Record Payment' not in other_page.content
        assert b'Settings' not in other_page.content

        for url in (
            reverse('salary_create'),
            reverse('salary_edit', args=[other.pk]),
            reverse('month_create', args=[other.pk]),
            reverse('payment_create', args=[other.pk]),
        ):
            assert client_logged_in.get(url).status_code == 403
            assert client_logged_in.post(url, {}).status_code == 403


class TestSalariesEdit:
    def test_can_create_month_and_payment_but_not_delete(
        self, client_logged_in, user, salaries_preset
    ):
        salaries_preset.salaries_edit = True
        salaries_preset.save(update_fields=['salaries_edit'])

        listed = client_logged_in.get(reverse('salary_list'))
        assert b'Add Employee' in listed.content

        created = client_logged_in.post(reverse('salary_create'), {
            'user': user.pk,
            'base_salary': '4200.00',
            'currency': 'EUR',
        })
        assert created.status_code == 200
        salary = EmployeeSalary.objects.get(user=user)
        assert salary.base_salary == Decimal('4200.00')

        month_response = client_logged_in.post(reverse('month_create', args=[salary.pk]), {
            'year': 2025,
            'month': 4,
            'expected_amount': '4200.00',
        })
        assert month_response.status_code == 200
        month = SalaryMonth.objects.get(employee_salary=salary, year=2025, month=4)

        payment_response = client_logged_in.post(reverse('payment_create', args=[salary.pk]), {
            'salary_month': month.pk,
            'amount': '1000.00',
            'payment_date': '2025-04-15',
            'payment_method': 'bank_transfer',
        })
        assert payment_response.status_code == 200
        payment = Payment.objects.get(salary_month=month)

        detail = client_logged_in.get(reverse('salary_detail', args=[salary.pk]))
        page = detail.content.decode()
        assert 'Record Payment' in page
        assert 'Add Month' in page
        assert 'Settings' in page
        assert 'Edit month' in page

        editor = client_logged_in.get(reverse('salary_edit', args=[salary.pk]))
        assert editor.status_code == 200
        assert b'Delete Salary Configuration' not in editor.content
        month_editor = client_logged_in.get(reverse('month_edit', args=[salary.pk, month.pk]))
        assert b'Delete Month' not in month_editor.content
        payment_editor = client_logged_in.get(
            reverse('payment_edit', args=[salary.pk, payment.pk])
        )
        assert b'Delete Payment' not in payment_editor.content

        hidden = _salary(_other_employee('edit-hidden@example.com', 'Edit Hidden'), '8000.00')
        assert client_logged_in.get(reverse('salary_detail', args=[hidden.pk])).status_code == 404
        assert client_logged_in.get(reverse('salary_edit', args=[hidden.pk])).status_code == 404
        assert client_logged_in.get(reverse('month_create', args=[hidden.pk])).status_code == 404
        assert client_logged_in.post(reverse('payment_create', args=[hidden.pk]), {}).status_code == 404

        for url in (
            reverse('salary_delete', args=[salary.pk]),
            reverse('month_delete', args=[salary.pk, month.pk]),
            reverse('payment_delete', args=[salary.pk, payment.pk]),
        ):
            assert client_logged_in.post(url).status_code == 403
        assert EmployeeSalary.objects.filter(pk=salary.pk).exists()
        assert SalaryMonth.objects.filter(pk=month.pk).exists()
        assert Payment.objects.filter(pk=payment.pk).exists()


class TestExtrasOff:
    def test_no_add_button_and_create_forbidden(self, client_logged_in, user, salaries_preset):
        assert salaries_preset.salaries_view_all is False
        assert salaries_preset.salaries_edit is False

        listed = client_logged_in.get(reverse('salary_list'))
        assert listed.status_code == 200
        assert b'Add Employee' not in listed.content
        assert b'Configure first employee salary' not in listed.content

        assert client_logged_in.get(reverse('salary_create')).status_code == 403
        posted = client_logged_in.post(reverse('salary_create'), {
            'user': user.pk,
            'base_salary': '1000.00',
            'currency': 'EUR',
        })
        assert posted.status_code == 403
        assert not EmployeeSalary.objects.filter(user=user).exists()


@pytest.mark.django_db
class TestAdminBypassesSalaryFlags:
    def test_admin_can_view_edit_and_delete_with_flags_off(self, client):
        preset = PermissionPreset.objects.create(
            name='Payroll Flags Off',
            access_salaries=True,
            salaries_view_all=False,
            salaries_edit=False,
        )
        admin = get_user_model().objects.create_user(
            email='payroll-admin@example.com',
            name='Payroll Admin',
            password='testpass123',
            role='admin',
            permission_preset=preset,
        )
        assert admin.has_app_permission('salaries_view_all') is True
        assert admin.has_app_permission('salaries_edit') is True
        employee = _other_employee('paid-employee@example.com', 'Paid Employee')
        salary = _salary(employee, '5500.00')
        month = SalaryMonth.objects.create(
            employee_salary=salary, year=2025, month=5, expected_amount=Decimal('5500.00')
        )
        payment = Payment.objects.create(
            salary_month=month, amount=Decimal('500.00'), payment_date='2025-05-10'
        )
        new_hire = _other_employee('new-hire@example.com', 'New Hire')
        client.force_login(admin)

        listed = client.get(reverse('salary_list'))
        assert listed.status_code == 200
        assert b'Paid Employee' in listed.content
        assert b'Add Employee' in listed.content
        assert client.get(reverse('salary_detail', args=[salary.pk])).status_code == 200

        edited = client.post(reverse('salary_edit', args=[salary.pk]), {
            'user': employee.pk,
            'base_salary': '6100.00',
            'currency': 'EUR',
        })
        assert edited.status_code == 200
        salary.refresh_from_db()
        assert salary.base_salary == Decimal('6100.00')
        assert b'Delete Salary Configuration' in client.get(
            reverse('salary_edit', args=[salary.pk])
        ).content
        assert b'Delete Month' in client.get(
            reverse('month_edit', args=[salary.pk, month.pk])
        ).content
        assert b'Delete Payment' in client.get(
            reverse('payment_edit', args=[salary.pk, payment.pk])
        ).content

        created = client.post(reverse('salary_create'), {
            'user': new_hire.pk,
            'base_salary': '2500.00',
            'currency': 'EUR',
        })
        assert created.status_code == 200
        assert EmployeeSalary.objects.filter(user=new_hire).exists()

        assert client.post(reverse('payment_delete', args=[salary.pk, payment.pk])).status_code == 200
        assert client.post(reverse('month_delete', args=[salary.pk, month.pk])).status_code == 200
        assert client.post(reverse('salary_delete', args=[salary.pk])).status_code == 200
        assert not Payment.objects.filter(pk=payment.pk).exists()
        assert not SalaryMonth.objects.filter(pk=month.pk).exists()
        assert not EmployeeSalary.objects.filter(pk=salary.pk).exists()

        preset.refresh_from_db()
        assert preset.salaries_view_all is False
        assert preset.salaries_edit is False
