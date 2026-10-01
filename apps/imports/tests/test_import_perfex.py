import io
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.permissions import PERMISSION_KEYS
from apps.clients.models import Client
from apps.crm.models import Company, Currency
from apps.invoices.models import Invoice, Payment
from apps.invoices.services import create_invoice
from apps.projects.models import Project
from apps.salaries.models import EmployeeSalary
from apps.salaries.models import Payment as SalaryPayment
from apps.tasks.models import Attachment, Task, TimeEntry

User = get_user_model()
LONG_TITLE = 'L' * 300


def dump_sql():
    short = 'X' * 250
    extra = 'Y' * 20
    return f"""
# TABLE STRUCTURE FOR: tblclients
CREATE TABLE `tblclients` (
  `userid` int NOT NULL
);
LOCK TABLES `tblclients` WRITE;

INSERT INTO `tblsessions` (`id`, `data`) VALUES ('s1', 'keep; going');
INSERT INTO `tblvault` (`id`, `password`) VALUES (1, 'secret');
INSERT INTO `tblproposals` (`id`, `subject`) VALUES (1, 'Keep; this');

INSERT INTO `tblstaff` (`staffid`, `email`, `firstname`, `lastname`, `password`, `datecreated`, `admin`, `active`) VALUES (1, 'admin@example.com', 'Perfex', 'Admin', 'secret;hash', '2019-01-01 00:00:00', 1, 1);
INSERT INTO `tblstaff` (`staffid`, `email`, `firstname`, `lastname`, `password`, `datecreated`, `admin`, `active`) VALUES (2, 'member@example.com', 'Perfex', 'Member', 'member-hash', '2019-02-01 00:00:00', 0, 1);

INSERT INTO `tbloptions` (`id`, `name`, `value`, `autoload`) VALUES (1, 'invoice_company_name', 'Web FTL Ltd', 1);
INSERT INTO `tbloptions` (`id`, `name`, `value`, `autoload`) VALUES (2, 'invoice_company_address', '1 High Street
Floor 2', 1);
INSERT INTO `tbloptions` (`id`, `name`, `value`, `autoload`) VALUES (3, 'invoice_company_city', 'London', 1);
INSERT INTO `tbloptions` (`id`, `name`, `value`, `autoload`) VALUES (4, 'invoice_company_postal_code', 'E1 1AA', 1);
INSERT INTO `tbloptions` (`id`, `name`, `value`, `autoload`) VALUES (5, 'invoice_company_country_code', 'UK', 1);
INSERT INTO `tbloptions` (`id`, `name`, `value`, `autoload`) VALUES (6, 'invoice_company_phonenumber', '+44 20 0000 0000', 1);
INSERT INTO `tbloptions` (`id`, `name`, `value`, `autoload`) VALUES (7, 'company_vat', 'GB123', 1);
INSERT INTO `tbloptions` (`id`, `name`, `value`, `autoload`) VALUES (8, 'company_email', 'billing@example.com', 1);
INSERT INTO `tbloptions` (`id`, `name`, `value`, `autoload`) VALUES (9, 'companyname', 'Fallback Name', 1);

INSERT INTO `tblcurrencies` (`id`, `symbol`, `name`, `placement`, `isdefault`) VALUES (1, '$', 'USD', 'before', 0);
INSERT INTO `tblcurrencies` (`id`, `symbol`, `name`, `placement`, `isdefault`) VALUES (2, '€', 'EUR', 'before', 0);
INSERT INTO `tblcurrencies` (`id`, `symbol`, `name`, `placement`, `isdefault`) VALUES (3, '£', 'GBP', 'before', 1);

INSERT INTO `tblcountries` (`country_id`, `short_name`) VALUES (235, 'United Kingdom');

INSERT INTO `tblclients` (`userid`, `company`, `vat`, `phonenumber`, `country`, `city`, `zip`, `state`, `address`, `datecreated`, `active`, `default_currency`) VALUES (1, 'Acme Ltd', 'GB999', '999', 235, 'London', 'SW1A 1AA', 'Greater London', '10 King Street', '2020-05-01 08:30:00', 1, 3);
INSERT INTO `tblclients` (`userid`, `company`, `vat`, `phonenumber`, `country`, `city`, `zip`, `state`, `address`, `datecreated`, `active`, `default_currency`) VALUES (2, 'No Currency Ltd', '', '222', 0, '', '', '', '', '2020-06-01 00:00:00', 1, 0);
INSERT INTO `tblclients` (`userid`, `company`, `vat`, `phonenumber`, `country`, `city`, `zip`, `state`, `address`, `datecreated`, `active`, `default_currency`) VALUES (3, 'No Invoices Ltd', '', '', 0, '', '', '', '', '2020-07-01 00:00:00', 1, 0);
INSERT INTO `tblclients` (`userid`, `company`, `vat`, `phonenumber`, `country`, `city`, `zip`, `state`, `address`, `datecreated`, `active`, `default_currency`) VALUES (4, 'Inactive Ltd', '', '', 0, '', '', '', '', '2020-08-01 00:00:00', 0, 2);

INSERT INTO `tblcontacts` (`id`, `userid`, `is_primary`, `firstname`, `lastname`, `email`, `phonenumber`) VALUES (1, 1, 1, 'Ada', 'Lovelace', 'ada@example.com', '111');
INSERT INTO `tblcontacts` (`id`, `userid`, `is_primary`, `firstname`, `lastname`, `email`, `phonenumber`) VALUES (2, 2, 1, 'Bea', 'Bell', 'bea@example.com', '');

INSERT INTO `tblprojects` (`id`, `name`, `description`, `clientid`, `project_created`) VALUES (1, 'Website', 'Rebuild', 1, '2024-01-02');

INSERT INTO `tbltasks` (`id`, `name`, `description`, `priority`, `dateadded`, `duedate`, `status`, `rel_id`, `rel_type`) VALUES (1, 'Ship homepage', 'Line one\\nLine two', 2, '2024-01-03 09:00:00', NULL, 5, 1, 'project');
INSERT INTO `tbltasks` (`id`, `name`, `description`, `priority`, `dateadded`, `duedate`, `status`, `rel_id`, `rel_type`) VALUES (2, '{LONG_TITLE}', '', 1, '2024-01-04 09:00:00', '2024-02-01', 1, 1, 'project');
INSERT INTO `tbltasks` (`id`, `name`, `description`, `priority`, `dateadded`, `duedate`, `status`, `rel_id`, `rel_type`) VALUES (3, 'Loose task', 'On the client', 3, '2024-01-05 09:00:00', '0000-00-00', 4, 1, 'customer');

INSERT INTO `tbltask_checklist_items` (`id`, `taskid`, `description`, `finished`, `list_order`) VALUES (1, 3, 'Sub item', 1, 1);
INSERT INTO `tbltaskstimers` (`id`, `task_id`, `start_time`, `end_time`, `staff_id`, `note`) VALUES (1, 3, '1700000000', '1700003600', 1, 'worked');
INSERT INTO `tbltaskstimers` (`id`, `task_id`, `start_time`, `end_time`, `staff_id`, `note`) VALUES (2, 1, '1700000000', NULL, 1, '');
INSERT INTO `tbltask_comments` (`id`, `content`, `taskid`, `staffid`, `file_id`, `dateadded`) VALUES (1, 'See the file', 1, 1, 9, '2024-01-06 10:00:00');
INSERT INTO `tblfiles` (`id`, `rel_id`, `rel_type`, `file_name`) VALUES (9, 1, 'task', 'brief.pdf');

INSERT INTO `tblpayment_modes` (`id`, `name`) VALUES (1, 'Bank');

INSERT INTO `tblinvoices` (`id`, `clientid`, `number`, `date`, `duedate`, `currency`, `adjustment`, `status`, `datecreated`, `subscription_id`, `billing_street`, `billing_city`, `billing_state`, `billing_zip`, `billing_country`, `datesend`) VALUES (1, 1, 10, '2024-03-01', '2024-03-15', 3, 0.00, 2, '2024-03-01 12:00:00', 0, '1 Bill St', 'London', '', '', 235, NULL);
INSERT INTO `tblinvoices` (`id`, `clientid`, `number`, `date`, `duedate`, `currency`, `adjustment`, `status`, `datecreated`, `subscription_id`, `billing_street`, `billing_city`, `billing_state`, `billing_zip`, `billing_country`, `datesend`) VALUES (2, 2, 11, '2024-04-01', '2024-04-15', 3, NULL, 2, '2024-04-01 12:00:00', 0, '2 Bill', '', '', '', 0, NULL);
INSERT INTO `tblinvoices` (`id`, `clientid`, `number`, `date`, `duedate`, `currency`, `adjustment`, `status`, `datecreated`, `subscription_id`, `billing_street`, `billing_city`, `billing_state`, `billing_zip`, `billing_country`, `datesend`) VALUES (3, 1, 12, '2024-05-01', '2024-05-15', 3, 0.00, 2, '2024-05-01 12:00:00', 9, 'Sub St', '', '', '', 0, NULL);
INSERT INTO `tblinvoices` (`id`, `clientid`, `number`, `date`, `duedate`, `currency`, `adjustment`, `status`, `datecreated`, `subscription_id`, `billing_street`, `billing_city`, `billing_state`, `billing_zip`, `billing_country`, `datesend`) VALUES (4, 1, 13, '2024-06-01', '2024-06-15', 3, 0.00, 5, '2024-06-01 12:00:00', 0, 'Can St', '', '', '', 0, NULL);
INSERT INTO `tblinvoices` (`id`, `clientid`, `number`, `date`, `duedate`, `currency`, `adjustment`, `status`, `datecreated`, `subscription_id`, `billing_street`, `billing_city`, `billing_state`, `billing_zip`, `billing_country`, `datesend`) VALUES (5, 1, 14, '2024-07-01', '2024-07-15', 3, -5.00, 1, '2024-07-01 12:00:00', 0, 'Adj St', '', '', '', 0, NULL);
INSERT INTO `tblinvoices` (`id`, `clientid`, `number`, `date`, `duedate`, `currency`, `adjustment`, `status`, `datecreated`, `subscription_id`, `billing_street`, `billing_city`, `billing_state`, `billing_zip`, `billing_country`, `datesend`) VALUES (6, 4, 15, '2024-08-01', '2024-08-15', 2, 0.00, 2, '2024-08-01 12:00:00', 0, 'Euro St', '', '', '', 0, NULL);

INSERT INTO `tblitemable` (`id`, `rel_id`, `rel_type`, `description`, `long_description`, `qty`, `rate`, `unit`, `item_order`) VALUES (1, 1, 'invoice', 'Hosting', 'Annual plan', 1, 100.00, 'month', 1);
INSERT INTO `tblitemable` (`id`, `rel_id`, `rel_type`, `description`, `long_description`, `qty`, `rate`, `unit`, `item_order`) VALUES (2, 1, 'invoice', '{short}', '{extra}', 1, 5.00, '', 2);
INSERT INTO `tblitemable` (`id`, `rel_id`, `rel_type`, `description`, `long_description`, `qty`, `rate`, `unit`, `item_order`) VALUES (3, 2, 'invoice', 'Work', '', 2, 50.00, '', 1);
INSERT INTO `tblitemable` (`id`, `rel_id`, `rel_type`, `description`, `long_description`, `qty`, `rate`, `unit`, `item_order`) VALUES (4, 3, 'invoice', 'Sub line', '', 1, 10.00, '', 1);
INSERT INTO `tblitemable` (`id`, `rel_id`, `rel_type`, `description`, `long_description`, `qty`, `rate`, `unit`, `item_order`) VALUES (5, 4, 'invoice', 'Cancelled line', '', 1, 10.00, '', 1);
INSERT INTO `tblitemable` (`id`, `rel_id`, `rel_type`, `description`, `long_description`, `qty`, `rate`, `unit`, `item_order`) VALUES (6, 5, 'invoice', 'Adjusted', '', 1, 80.00, '', 1);
INSERT INTO `tblitemable` (`id`, `rel_id`, `rel_type`, `description`, `long_description`, `qty`, `rate`, `unit`, `item_order`) VALUES (7, 6, 'invoice', 'Euro work', '', 1, 40.00, '', 1);
INSERT INTO `tblitemable` (`id`, `rel_id`, `rel_type`, `description`, `long_description`, `qty`, `rate`, `unit`, `item_order`) VALUES (8, 99, 'proposal', 'Proposal line', 'nope', 1, 5.00, '', 1);

INSERT INTO `tblinvoicepaymentrecords` (`id`, `invoiceid`, `amount`, `paymentmode`, `date`, `daterecorded`, `note`, `transactionid`) VALUES (1, 1, 105.00, '1', '2024-03-02', '2024-03-02 15:00:00', '', 'txn_10');
INSERT INTO `tblinvoicepaymentrecords` (`id`, `invoiceid`, `amount`, `paymentmode`, `date`, `daterecorded`, `note`, `transactionid`) VALUES (2, 2, 100.00, 'stripe', '2024-04-02', '2024-04-02 15:00:00', '', 'pi_11');
INSERT INTO `tblinvoicepaymentrecords` (`id`, `invoiceid`, `amount`, `paymentmode`, `date`, `daterecorded`, `note`, `transactionid`) VALUES (3, 3, 10.00, '1', '2024-05-02', '2024-05-02 15:00:00', '', '');
INSERT INTO `tblinvoicepaymentrecords` (`id`, `invoiceid`, `amount`, `paymentmode`, `date`, `daterecorded`, `note`, `transactionid`) VALUES (4, 6, 40.00, '1', '2024-08-02', '2024-08-02 15:00:00', '', '');

INSERT INTO `tblstaff_salaries` (`id`, `staff_id`, `amount`, `currency_id`, `effective_date`) VALUES (1, 2, 2500.00, 3, '2026-01-01');
INSERT INTO `tblstaff_salaries` (`id`, `staff_id`, `amount`, `currency_id`, `effective_date`) VALUES (2, 2, 4000.00, 1, '2025-06-01');
INSERT INTO `tblstaff_salary_payments` (`id`, `staff_id`, `amount`, `currency_id`, `payment_date`, `note`) VALUES (1, 2, 1000.00, 3, '2026-01-15', 'first');
INSERT INTO `tblstaff_salary_payments` (`id`, `staff_id`, `amount`, `currency_id`, `payment_date`, `note`) VALUES (2, 2, 1500.00, 3, '2026-01-28', 'second');
INSERT INTO `tblstaff_salary_payments` (`id`, `staff_id`, `amount`, `currency_id`, `payment_date`, `note`) VALUES (3, 2, 4000.00, 1, '2025-06-15', 'usd');
"""


def _kept_admin():
    return User.objects.create_user(
        email='admin@example.com',
        name='Kept Admin',
        password='original-pass',
        role='admin',
    )


def _run(sql, path, *, commit):
    out = io.StringIO()
    kwargs = {
        'stdout': out,
        'admin_password': 'admin-pass',
        'member_password': 'member-pass',
    }
    if commit:
        path.write_text(sql, encoding='utf-8')
        call_command('import_perfex', str(path), commit=True, **kwargs)
    else:
        with patch('sys.stdin', io.StringIO(sql)):
            call_command('import_perfex', '-', **kwargs)
    return out.getvalue()


@pytest.mark.django_db
def test_dry_run_leaves_nothing(tmp_path):
    admin = _kept_admin()
    report = _run(dump_sql(), tmp_path / 'unused.sql', commit=False)

    assert 'Dry run. Rolled back.' in report
    assert 'clients: 4' in report
    assert 'subscription invoice: 1' in report
    admin.refresh_from_db()
    assert admin.name == 'Kept Admin'
    assert admin.check_password('original-pass')
    assert User.objects.filter(email='member@example.com').count() == 0
    assert Client.objects.count() == 0
    assert Project.objects.count() == 0
    assert Task.objects.count() == 0
    assert Invoice.objects.count() == 0
    assert EmployeeSalary.objects.count() == 0
    assert not Company.objects.filter(legal_name='Web FTL Ltd').exists()


@pytest.mark.django_db
def test_commit_maps_the_fabricated_dump(tmp_path):
    admin = _kept_admin()
    report = _run(dump_sql(), tmp_path / 'dump.sql', commit=True)

    assert 'Committed.' in report
    assert 'subscription invoice: 1' in report
    assert 'cancelled invoice: 1' in report
    assert 'negative adjustment: 1' in report
    assert 'usd salary: 1' in report
    assert 'usd salary payment: 1' in report
    assert 'open timer: 1' in report
    assert 'proposal line: 1' in report
    assert 'task file: 1' in report

    admin.refresh_from_db()
    assert admin.name == 'Kept Admin'
    assert admin.role == 'admin'
    assert admin.check_password('original-pass')
    assert not admin.check_password('secret;hash')

    member = User.objects.get(email='member@example.com')
    assert member.name == 'Perfex Member'
    assert member.role == 'member'
    assert member.check_password('member-pass')
    assert member.password != 'member-hash'
    preset = member.permission_preset
    assert preset.name == 'Salaries'
    for key in PERMISSION_KEYS:
        expected = key in ('access_dashboard', 'access_salaries')
        assert getattr(preset, key) is expected

    acme = Client.objects.get(name='Acme Ltd')
    assert acme.email == 'ada@example.com'
    assert acme.phone == '111'
    assert acme.tax_id == 'GB999'
    assert acme.address == '10 King Street, London, Greater London, SW1A 1AA, United Kingdom'
    assert acme.currency.code == 'GBP'
    assert acme.created_by == admin
    assert acme.created_at == datetime(2020, 5, 1, 8, 30, tzinfo=UTC)

    unset_with_invoices = Client.objects.get(name='No Currency Ltd')
    assert unset_with_invoices.currency.code == 'GBP'
    assert unset_with_invoices.email == 'bea@example.com'
    assert unset_with_invoices.phone == ''

    assert Client.objects.get(name='No Invoices Ltd').currency_id is None
    inactive = Client.objects.get(name='Inactive Ltd')
    euro = Currency.objects.get(code='EUR')
    assert euro.symbol_before is False
    assert euro.name == 'Euro'
    assert euro.symbol == '€'
    assert inactive.currency_id == euro.pk

    company = Company.load()
    assert company.legal_name == 'Web FTL Ltd'
    assert company.email == 'billing@example.com'
    assert company.phone == '+44 20 0000 0000'
    assert company.tax_id == 'GB123'
    assert '1 High Street' in company.address
    assert 'Floor 2' in company.address
    assert 'London' in company.address

    website = Project.objects.get(name='Website')
    assert website.client == acme
    assert website.description == 'Rebuild'
    assert website.created_at == datetime(2024, 1, 2, tzinfo=UTC)
    assert Project.objects.filter(name='Imported tasks').count() == 1
    assert admin.project_access.count() == 2
    assert member.project_access.count() == 0

    ship = Task.objects.get(title='Ship homepage')
    assert ship.status.name == 'Done'
    assert ship.status.is_completed is True
    assert ship.priority == 'medium'
    assert ship.description == 'Line one\nLine two'
    assert ship.assignee == admin
    assert ship.created_at == datetime(2024, 1, 3, 9, 0, tzinfo=UTC)
    comment = ship.activities.get()
    assert comment.activity_type == 'comment'
    assert comment.content == 'See the file'
    assert comment.user == admin
    assert Attachment.objects.count() == 0

    long = Task.objects.get(title=LONG_TITLE)
    assert len(long.title) == 300
    assert long.status.name == 'To Do'
    assert long.priority == 'low'
    assert long.due_date == date(2024, 2, 1)

    loose = Task.objects.get(title='Loose task')
    assert loose.project.name == 'Imported tasks'
    assert loose.project.client == acme
    assert loose.status.name == 'In Progress'
    assert loose.priority == 'high'
    assert loose.due_date is None
    assert loose.assignee == admin
    subtask = loose.subtasks.get()
    assert subtask.title == 'Sub item'
    assert subtask.completed is True
    entry = loose.time_entries.get()
    assert entry.note == 'worked'
    assert entry.user == admin
    assert entry.ended_at - entry.started_at == timedelta(hours=1)
    assert TimeEntry.objects.count() == 1

    paid = Invoice.objects.get(number=10)
    assert paid.status == 'paid'
    assert paid.is_draft is False
    assert paid.sent_at == datetime(2024, 3, 1, 12, 0, tzinfo=UTC)
    assert paid.created_at == paid.sent_at
    assert paid.tax_rate == Decimal('0.00')
    assert paid.currency_code == 'GBP'
    assert paid.currency_symbol == '£'
    assert paid.symbol_before is True
    assert paid.bill_to_name == 'Acme Ltd'
    assert paid.bill_to_tax_id == 'GB999'
    assert paid.bill_to_address == '1 Bill St, London, United Kingdom'
    assert paid.company_legal_name == 'Web FTL Ltd'
    assert list(paid.lines.values_list('description', flat=True)) == [
        'Hosting\nAnnual plan',
        'X' * 250,
    ]
    assert 'month' not in paid.lines.get(description__startswith='Hosting').description
    assert paid.payments.get().note == 'Bank · txn_10'

    gbp_invoice = Invoice.objects.get(number=11)
    assert gbp_invoice.client == unset_with_invoices
    assert gbp_invoice.status == 'paid'
    assert gbp_invoice.payments.get().note == 'stripe · pi_11'

    assert not Invoice.objects.filter(number__in=[12, 13, 14]).exists()

    euro_invoice = Invoice.objects.get(number=15)
    assert euro_invoice.status == 'paid'
    assert euro_invoice.currency_code == 'EUR'
    assert euro_invoice.currency_symbol == '€'
    assert euro_invoice.symbol_before is False
    assert Payment.objects.count() == 3

    later = create_invoice(
        client=acme,
        issue_date=date(2026, 1, 1),
        due_date=date(2026, 1, 15),
        tax_rate=Decimal('0'),
    )
    assert later.number == 16

    salary = EmployeeSalary.objects.get()
    assert salary.user == member
    assert salary.currency == 'GBP'
    assert salary.base_salary == Decimal('2500.00')
    month = salary.months.get()
    assert (month.year, month.month) == (2026, 1)
    assert month.expected_amount == Decimal('2500.00')
    assert month.status == 'paid'
    pays = list(month.payments.order_by('payment_date'))
    assert [pay.amount for pay in pays] == [Decimal('1000.00'), Decimal('1500.00')]
    assert [pay.payment_method for pay in pays] == ['other', 'other']
    assert [pay.notes for pay in pays] == ['first', 'second']
    assert SalaryPayment.objects.count() == 2


@pytest.mark.django_db
def test_existing_company_is_left_in_place(tmp_path):
    _kept_admin()
    Company.objects.create(
        legal_name='Existing Co',
        address='Kept address',
        email='kept@example.com',
        phone='1',
        tax_id='KEEP',
    )
    report = _run(dump_sql(), tmp_path / 'dump.sql', commit=True)

    assert 'company: 0' in report
    company = Company.load()
    assert company.legal_name == 'Existing Co'
    assert company.address == 'Kept address'
    assert company.email == 'kept@example.com'
    paid = Invoice.objects.get(number=10)
    assert paid.company_legal_name == 'Existing Co'
    assert paid.company_address == 'Kept address'


@pytest.mark.django_db
def test_import_stops_when_a_client_exists(tmp_path):
    Client.objects.create(name='Already')
    with pytest.raises(CommandError, match='client already exists'):
        _run(dump_sql(), tmp_path / 'dump.sql', commit=True)
    assert list(Client.objects.values_list('name', flat=True)) == ['Already']


@pytest.mark.django_db
def test_unknown_task_status_rolls_back(tmp_path):
    sql = """
INSERT INTO `tblstaff` (`staffid`, `email`, `firstname`, `lastname`, `password`, `datecreated`, `admin`, `active`) VALUES (1, 'admin@example.com', 'A', 'B', 'hash', '2019-01-01 00:00:00', 1, 1);
INSERT INTO `tblclients` (`userid`, `company`, `vat`, `phonenumber`, `country`, `city`, `zip`, `state`, `address`, `datecreated`, `active`, `default_currency`) VALUES (1, 'Acme', '', '', 0, '', '', '', '', '2020-01-01 00:00:00', 1, 0);
INSERT INTO `tbltasks` (`id`, `name`, `description`, `priority`, `dateadded`, `duedate`, `status`, `rel_id`, `rel_type`) VALUES (1, 'Bad', '', 2, '2020-01-02 00:00:00', NULL, 3, 1, 'customer');
"""
    with pytest.raises(CommandError, match='Unknown Perfex task status 3'):
        _run(sql, tmp_path / 'dump.sql', commit=True)
    assert Client.objects.count() == 0
    assert Task.objects.count() == 0
    assert User.objects.filter(email='admin@example.com').count() == 0


def test_sql_dumps_stay_out_of_the_image():
    lines = Path('.dockerignore').read_text().splitlines()
    assert '*.sql' in {line.strip() for line in lines}


def test_entrypoint_does_not_run_the_import():
    assert 'import_perfex' not in Path('entrypoint.sh').read_text()


@pytest.mark.django_db
def test_imported_closed_tasks_close_on_their_finish_date(tmp_path):
    """Imported Done tasks keep their Perfex date, so old ones archive at once
    instead of all landing on the board for two more weeks."""
    original = (
        "INSERT INTO `tbltasks` (`id`, `name`, `description`, `priority`, `dateadded`, `duedate`, `status`, "
        "`rel_id`, `rel_type`) VALUES (1, 'Ship homepage', 'Line one\\nLine two', 2, '2024-01-03 09:00:00', "
        "NULL, 5, 1, 'project');"
    )
    finished = (
        "INSERT INTO `tbltasks` (`id`, `name`, `description`, `priority`, `dateadded`, `duedate`, `status`, "
        "`rel_id`, `rel_type`, `datefinished`) VALUES (1, 'Ship homepage', 'Line one\\nLine two', 2, "
        "'2024-01-03 09:00:00', NULL, 5, 1, 'project', '2024-02-10 17:00:00');"
    )
    sql = dump_sql()
    assert original in sql
    _run(sql.replace(original, finished), tmp_path / 'dump.sql', commit=True)

    ship = Task.objects.get(title='Ship homepage')
    assert ship.closed_at is not None and ship.closed_at.date() == date(2024, 2, 10)
    assert ship.is_archived
    assert all(task.closed_at is None for task in Task.objects.exclude(status__category__in=['completed', 'canceled']))
