"""Load a parsed Perfex dump into WebFTL.

Dry-run and ``--commit`` both write inside one transaction. The command rolls
that transaction back unless ``--commit`` was passed. ``created_at`` and
``updated_at`` are applied with ``QuerySet.update`` because ``auto_now_add``
and ``auto_now`` ignore values passed to ``create()``.
"""

from datetime import UTC, date, datetime, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.db.models.signals import post_save
from django.utils import timezone

from apps.accounts.permissions import PERMISSION_KEYS, PermissionPreset
from apps.clients.models import Client
from apps.crm.models import Company, Currency
from apps.invoices.models import Invoice, InvoiceLine
from apps.invoices.models import Payment as InvoicePayment
from apps.projects.models import Project, ProjectAccess, Status
from apps.salaries.models import EmployeeSalary, SalaryMonth
from apps.salaries.models import Payment as SalaryPayment
from apps.tasks.models import Subtask, Task, TaskActivity, TimeEntry
from apps.tasks.signals import log_task_changes

User = get_user_model()

WROTE_KEYS = (
    'users',
    'company',
    'clients',
    'projects',
    'project access',
    'tasks',
    'subtasks',
    'comments',
    'timers',
    'invoices',
    'invoice lines',
    'invoice payments',
    'salaries',
    'salary months',
    'salary payments',
)

HOLDING_PROJECT = 'Imported tasks'
MEMBER_PRESET = 'Salaries'

# Perfex task status ids. Anything else stops the import.
TASK_STATUS = {
    1: 'To Do',
    4: 'In Progress',
    2: 'Review',
    5: 'Done',
}
TASK_PRIORITY = {
    1: 'low',
    2: 'medium',
    3: 'high',
    4: 'urgent',
}

INVOICE_CANCELLED = 5
INVOICE_DRAFT = 6

# WebFTL keeps these placements. An existing Currency row is not rewritten,
# so a euro symbol that already sits after the amount stays there.
SYMBOL_BEFORE = {'EUR': False, 'RON': False}
CURRENCY_DEFAULTS = {
    'USD': ('US Dollar', '$'),
    'EUR': ('Euro', '€'),
    'GBP': ('British Pound', '£'),
    'RON': ('Romanian Leu', 'lei'),
}
SYMBOL_CODES = {'$': 'USD', '€': 'EUR', '£': 'GBP', 'lei': 'RON'}

_EMPTY_DATES = {'', '0000-00-00', '0000-00-00 00:00:00'}
_CENTS = Decimal('0.01')


class Stats:
    def __init__(self):
        self.wrote = {key: 0 for key in WROTE_KEYS}
        self.skipped = {}

    def add(self, key, count=1):
        self.wrote[key] += count

    def skip(self, reason):
        self.skipped[reason] = self.skipped.get(reason, 0) + 1


def format_report(stats, *, committed):
    lines = ['Committed.' if committed else 'Dry run. Rolled back.']
    lines.append('Wrote:')
    for key in WROTE_KEYS:
        lines.append(f'  {key}: {stats.wrote[key]}')
    lines.append('Skipped:')
    if not stats.skipped:
        lines.append('  (none)')
    else:
        for reason in sorted(stats.skipped):
            lines.append(f'  {reason}: {stats.skipped[reason]}')
    return '\n'.join(lines)


def load_dump(tables, *, admin_password, member_password):
    stats = Stats()
    users, admin = import_users(
        tables['tblstaff'], admin_password, member_password, stats
    )
    options = {
        str(row.get('name') or '').strip(): row.get('value') or ''
        for row in tables['tbloptions']
    }
    currencies = load_currencies(tables['tblcurrencies'])
    company = load_company(options, stats)
    countries = load_countries(tables['tblcountries'])
    clients = import_clients(
        tables['tblclients'],
        tables['tblcontacts'],
        countries,
        currencies,
        tables['tblinvoices'],
        admin,
        stats,
    )
    projects = import_projects(tables['tblprojects'], clients, admin, stats)
    tasks = import_tasks(tables['tbltasks'], projects, clients, admin, stats)
    import_subtasks(tables['tbltask_checklist_items'], tasks, stats)
    import_comments(tables['tbltask_comments'], tasks, users, stats)
    import_timers(tables['tbltaskstimers'], tasks, users, stats)
    import_invoices(
        tables['tblinvoices'],
        tables['tblitemable'],
        tables['tblinvoicepaymentrecords'],
        tables['tblpayment_modes'],
        clients,
        countries,
        currencies,
        company,
        stats,
    )
    import_salaries(
        tables['tblstaff_salaries'],
        tables['tblstaff_salary_payments'],
        currencies,
        users,
        stats,
    )
    for _row in tables['tblfiles']:
        stats.skip('task file')
    return stats


def import_users(rows, admin_password, member_password, stats):
    users = {}
    preset = None
    for row in sorted(rows, key=lambda item: as_int(item.get('staffid'), 0)):
        staff_id = str(row.get('staffid'))
        email = str(row.get('email') or '').strip()
        if not email:
            raise CommandError(f'Staff {staff_id} is missing an email.')
        existing = User.objects.filter(email__iexact=email).first()
        if existing is not None:
            users[staff_id] = existing
            continue
        role = 'admin' if as_int(row.get('admin'), 0) == 1 else 'member'
        if role == 'admin':
            if not admin_password:
                raise CommandError('Pass --admin-password to create the Perfex admin.')
            password = admin_password
            permission_preset = None
        else:
            if not member_password:
                raise CommandError('Pass --member-password to create the Perfex member.')
            password = member_password
            if preset is None:
                preset = member_preset()
            permission_preset = preset
        first = str(row.get('firstname') or '').strip()
        last = str(row.get('lastname') or '').strip()
        name = ' '.join(part for part in (first, last) if part) or email
        user = User.objects.create_user(
            email=email,
            password=password,
            name=name[:255],
            role=role,
            is_active=as_int(row.get('active'), 1) == 1,
            permission_preset=permission_preset,
        )
        created = as_datetime(row.get('datecreated'))
        stamp(User, user.pk, created_at=created, updated_at=created)
        users[staff_id] = user
        stats.add('users')

    admins = [row for row in rows if as_int(row.get('admin'), 0) == 1]
    if not admins:
        raise CommandError('The dump has no Perfex admin.')
    admins.sort(key=lambda row: as_int(row.get('staffid'), 0))
    return users, users[str(admins[0].get('staffid'))]


def member_preset():
    """A preset with dashboard and salaries only. Other flags stay off."""
    flags = {key: False for key in PERMISSION_KEYS}
    flags['access_dashboard'] = True
    flags['access_salaries'] = True
    preset = PermissionPreset.objects.filter(name=MEMBER_PRESET).first()
    if preset is not None:
        if all(getattr(preset, key) is value for key, value in flags.items()):
            return preset
        raise CommandError(
            f'A permission preset named {MEMBER_PRESET} already exists with other flags.'
        )
    return PermissionPreset.objects.create(
        name=MEMBER_PRESET,
        description='Dashboard and salaries',
        **flags,
    )


def load_currencies(rows):
    mapping = {}
    for row in rows:
        code = perfex_currency_code(row)
        mapping[str(row.get('id'))] = ensure_currency(code, str(row.get('symbol') or '').strip())
    return mapping


def perfex_currency_code(row):
    name = str(row.get('name') or '').strip().upper()
    if len(name) == 3 and name.isalpha():
        return name
    symbol = str(row.get('symbol') or '').strip()
    code = SYMBOL_CODES.get(symbol)
    if not code:
        raise CommandError(f'Cannot map Perfex currency {name or symbol!r}.')
    return code


def ensure_currency(code, perfex_symbol):
    existing = Currency.objects.filter(code=code).first()
    if existing is not None:
        return existing
    name, symbol = CURRENCY_DEFAULTS.get(code, (code, perfex_symbol or code))
    currency = Currency(
        code=code,
        name=name,
        symbol=symbol or code,
        symbol_before=SYMBOL_BEFORE.get(code, True),
    )
    currency.save()
    return currency


def load_company(options, stats):
    """Fill the company from tbloptions only when legal_name is still empty."""
    company = Company.objects.filter(pk=1).first()
    if company is not None and company.legal_name.strip():
        return company
    filled = company_from_options(options)
    if company is None:
        company = Company(pk=1)
    if any(filled.values()):
        for key, value in filled.items():
            setattr(company, key, value)
        company.save()
        stats.add('company')
    return company


def company_from_options(options):
    def opt(*keys):
        for key in keys:
            value = str(options.get(key) or '').strip()
            if value:
                return value
        return ''

    email = opt('company_email', 'invoice_company_email')
    if '@' not in email:
        email = ''
    return {
        'legal_name': clip(opt('invoice_company_name', 'companyname'), 255),
        'address': join_address([
            opt('invoice_company_address'),
            opt('invoice_company_city'),
            opt('company_state'),
            opt('invoice_company_postal_code'),
            opt('invoice_company_country_code'),
        ]),
        'email': clip(email, 254),
        'phone': clip(opt('invoice_company_phonenumber'), 50),
        'tax_id': clip(opt('company_vat'), 64),
    }


def load_countries(rows):
    countries = {}
    for row in rows:
        country_id = row.get('country_id', row.get('id'))
        if country_id is None:
            continue
        name = str(row.get('short_name') or row.get('long_name') or '').strip()
        countries[str(country_id)] = name
    return countries


def import_clients(rows, contacts, countries, currencies, invoices, admin, stats):
    by_id = {}
    for row in sorted(rows, key=lambda item: as_int(item.get('userid'), 0)):
        client_id = str(row.get('userid'))
        name = str(row.get('company') or '').strip()
        if not name:
            raise CommandError('A client is missing a company name.')
        if len(name) > 255:
            raise CommandError('A client name is longer than 255 characters.')
        contact = contact_for(client_id, contacts)
        email = ''
        phone = ''
        if contact is not None:
            email = clip(contact.get('email'), 254)
            phone = clip(contact.get('phonenumber'), 50)
        client = Client(
            name=name,
            email=email,
            phone=phone,
            address=join_address([
                row.get('address'),
                row.get('city'),
                row.get('state'),
                row.get('zip'),
                countries.get(str(row.get('country') or '')),
            ]),
            tax_id=clip(row.get('vat'), 64),
            currency=currency_for_client(row, client_id, currencies, invoices),
            created_by=admin,
        )
        client.save()
        created = as_datetime(row.get('datecreated'))
        stamp(Client, client.pk, created_at=created, updated_at=created)
        by_id[client_id] = client
        stats.add('clients')
    return by_id


def contact_for(client_id, contacts):
    rows = [row for row in contacts if str(row.get('userid')) == client_id]
    if not rows:
        return None
    primary = [row for row in rows if as_int(row.get('is_primary'), 0) == 1]
    return (primary or rows)[0]


def currency_for_client(row, client_id, currencies, invoices):
    """Use the Perfex currency, or the invoice currency when the client has none.

    Two clients in the source dump have no currency and only GBP invoices.
    Three have neither, and stay unset. A client is not given a currency when
    its invoices disagree.
    """
    default = as_int(row.get('default_currency'), 0)
    if default:
        currency = currencies.get(str(default))
        if currency is None:
            raise CommandError(f'Client currency {default} is not in the dump.')
        return currency
    codes = []
    for invoice in invoices:
        if str(invoice.get('clientid')) != client_id:
            continue
        currency = currencies.get(str(invoice.get('currency')))
        if currency is not None:
            codes.append(currency.code)
    unique = set(codes)
    if len(unique) != 1:
        return None
    code = next(iter(unique))
    return next(currency for currency in currencies.values() if currency.code == code)


def import_projects(rows, clients, admin, stats):
    by_id = {}
    for row in sorted(rows, key=lambda item: as_int(item.get('id'), 0)):
        client = clients.get(str(row.get('clientid')))
        if client is None:
            raise CommandError(f'Project {row.get("id")} points at a missing client.')
        name = str(row.get('name') or '').strip()
        if not name:
            raise CommandError(f'Project {row.get("id")} is missing a name.')
        if len(name) > 255:
            raise CommandError(f'Project {name!r} is longer than 255 characters.')
        project = Project(
            client=client,
            name=name,
            description=str(row.get('description') or ''),
        )
        project.save()
        created = as_datetime(row.get('project_created'))
        stamp(Project, project.pk, created_at=created, updated_at=created)
        grant(project, admin, stats)
        by_id[str(row.get('id'))] = project
        stats.add('projects')
    return by_id


def grant(project, admin, stats):
    _access, created = ProjectAccess.objects.get_or_create(project=project, user=admin)
    if created:
        stats.add('project access')


def import_tasks(rows, projects, clients, admin, stats):
    # Saving a task normally writes a "created" activity stamped now. These
    # tasks already have their Perfex dates, and comments are imported separately.
    post_save.disconnect(log_task_changes, sender=Task)
    try:
        return _import_tasks(rows, projects, clients, admin, stats)
    finally:
        post_save.connect(log_task_changes, sender=Task)


def _import_tasks(rows, projects, clients, admin, stats):
    by_id = {}
    holding = {}
    ordered = sorted(rows, key=lambda item: as_int(item.get('id'), 0))
    for index, row in enumerate(ordered):
        title = str(row.get('name') or '').strip()
        if not title:
            raise CommandError(f'Task {row.get("id")} is missing a title.')
        if len(title) > 1000:
            raise CommandError('A task title is longer than 1000 characters.')
        project = task_project(row, projects, clients, holding, admin, stats)
        status_id = as_int(row.get('status'), None)
        status_name = TASK_STATUS.get(status_id)
        if status_name is None:
            raise CommandError(f'Unknown Perfex task status {row.get("status")}.')
        try:
            status = project.statuses.get(name=status_name)
        except Status.DoesNotExist as exc:
            raise CommandError(f'{project} is missing the {status_name} status.') from exc
        task = Task(
            project=project,
            status=status,
            title=title,
            description=str(row.get('description') or ''),
            assignee=admin,
            priority=priority_for(row.get('priority')),
            due_date=as_date(row.get('duedate')),
            order=index,
        )
        task.save()
        created = as_datetime(row.get('dateadded'))
        finished = as_datetime(row.get('datefinished'))
        stamp(Task, task.pk, created_at=created, updated_at=finished or created)
        by_id[str(row.get('id'))] = task
        stats.add('tasks')
    return by_id


def task_project(row, projects, clients, holding, admin, stats):
    rel_type = str(row.get('rel_type') or '').strip().lower()
    rel_id = str(row.get('rel_id'))
    if rel_type == 'project':
        project = projects.get(rel_id)
        if project is None:
            raise CommandError(f'Task {row.get("id")} points at a missing project.')
        return project
    if rel_type == 'customer':
        client = clients.get(rel_id)
        if client is None:
            raise CommandError(f'Task {row.get("id")} points at a missing client.')
        project = holding.get(client.pk)
        if project is None:
            project = Project(client=client, name=HOLDING_PROJECT, description='')
            project.save()
            grant(project, admin, stats)
            stats.add('projects')
            holding[client.pk] = project
        return project
    raise CommandError(f'Unknown task rel_type {rel_type!r}.')


def priority_for(value):
    if value is None or str(value).strip() in ('', '0'):
        return ''
    code = as_int(value, None)
    priority = TASK_PRIORITY.get(code)
    if priority is None:
        raise CommandError(f'Unknown Perfex task priority {value}.')
    return priority


def import_subtasks(rows, tasks, stats):
    ordered = sorted(
        rows,
        key=lambda item: (as_int(item.get('list_order'), 0), as_int(item.get('id'), 0)),
    )
    for row in ordered:
        task = tasks.get(str(row.get('taskid')))
        if task is None:
            raise CommandError(f'Subtask {row.get("id")} points at a missing task.')
        title = str(row.get('description') or '').strip()
        if not title:
            raise CommandError(f'Subtask {row.get("id")} is missing a title.')
        if len(title) > 255:
            raise CommandError('A subtask title is longer than 255 characters.')
        Subtask.objects.create(
            task=task,
            title=title,
            completed=as_int(row.get('finished'), 0) == 1,
            order=as_int(row.get('list_order'), 0),
        )
        stats.add('subtasks')


def import_comments(rows, tasks, users, stats):
    for row in sorted(rows, key=lambda item: as_int(item.get('id'), 0)):
        task = tasks.get(str(row.get('taskid')))
        if task is None:
            raise CommandError(f'Comment {row.get("id")} points at a missing task.')
        # A comment that points at a file keeps its text. The file bytes are not
        # in the dump, so no attachment is created.
        activity = TaskActivity.objects.create(
            task=task,
            user=users.get(str(row.get('staffid'))),
            activity_type='comment',
            content=str(row.get('content') or ''),
        )
        stamp(TaskActivity, activity.pk, created_at=as_datetime(row.get('dateadded')))
        stats.add('comments')


def import_timers(rows, tasks, users, stats):
    for row in sorted(rows, key=lambda item: as_int(item.get('id'), 0)):
        ended = as_unix(row.get('end_time'))
        if ended is None:
            stats.skip('open timer')
            continue
        task = tasks.get(str(row.get('task_id')))
        if task is None:
            raise CommandError(f'Timer {row.get("id")} points at a missing task.')
        started = as_unix(row.get('start_time'))
        if started is None:
            raise CommandError(f'Timer {row.get("id")} is missing a start time.')
        user = users.get(str(row.get('staff_id')))
        if user is None:
            raise CommandError(f'Timer {row.get("id")} points at a missing staff member.')
        TimeEntry.objects.create(
            task=task,
            user=user,
            started_at=started,
            ended_at=ended,
            note=str(row.get('note') or ''),
        )
        stats.add('timers')


def import_invoices(
    rows, lines, payments, modes, clients, countries, currencies, company, stats
):
    for row in lines:
        if str(row.get('rel_type') or '').lower() != 'invoice':
            stats.skip('proposal line')
    mode_names = {str(row.get('id')): str(row.get('name') or '').strip() for row in modes}
    ordered = sorted(rows, key=lambda item: as_int(item.get('number'), 0))
    for row in ordered:
        reason = invoice_skip_reason(row)
        if reason:
            stats.skip(reason)
            continue
        write_invoice(row, lines, payments, mode_names, clients, countries, currencies, company, stats)


def invoice_skip_reason(row):
    if id_set(row.get('subscription_id')):
        return 'subscription invoice'
    if as_int(row.get('status'), 0) == INVOICE_CANCELLED:
        return 'cancelled invoice'
    adjustment = as_decimal(row.get('adjustment'))
    if adjustment is not None and adjustment < 0:
        return 'negative adjustment'
    return None


def write_invoice(row, lines, payments, modes, clients, countries, currencies, company, stats):
    number = as_int(row.get('number'), None)
    if not number:
        raise CommandError('An invoice is missing a number.')
    client = clients.get(str(row.get('clientid')))
    if client is None:
        raise CommandError(f'Invoice {number} points at a missing client.')
    currency = currencies.get(str(row.get('currency')))
    if currency is None:
        raise CommandError(f'Invoice {number} has an unknown currency.')
    issue_date = as_date(row.get('date'))
    if issue_date is None:
        raise CommandError(f'Invoice {number} is missing an issue date.')
    due_date = as_date(row.get('duedate')) or issue_date
    invoice_id = str(row.get('id'))
    # Lines cannot be added after sent_at is set, so the invoice is stored
    # unsent, then lines, then payments, and only then sent_at.
    invoice = Invoice(
        client=client,
        number=number,
        issue_date=issue_date,
        due_date=due_date,
        tax_rate=Decimal('0.00'),
        bill_to_name=client.name,
        bill_to_email=clip(client.email, 254),
        bill_to_address=join_address([
            row.get('billing_street'),
            row.get('billing_city'),
            row.get('billing_state'),
            row.get('billing_zip'),
            countries.get(str(row.get('billing_country') or '')),
        ]),
        bill_to_tax_id=clip(client.tax_id, 64),
        company_legal_name=company.legal_name,
        company_address=company.address,
        company_email=company.email,
        company_phone=company.phone,
        company_tax_id=company.tax_id,
        currency_code=currency.code,
        currency_symbol=currency.symbol,
        symbol_before=currency.symbol_before,
    )
    invoice.save()
    stats.add('invoices')

    own_lines = [
        line for line in lines
        if str(line.get('rel_id')) == invoice_id
        and str(line.get('rel_type') or '').lower() == 'invoice'
    ]
    own_lines.sort(key=lambda item: (as_int(item.get('item_order'), 0), as_int(item.get('id'), 0)))
    for line in own_lines:
        InvoiceLine.objects.create(
            invoice=invoice,
            project=None,
            description=line_description(line),
            quantity=money_amount(line.get('qty')),
            unit_price=money_amount(line.get('rate')),
        )
        stats.add('invoice lines')

    own_payments = [payment for payment in payments if str(payment.get('invoiceid')) == invoice_id]
    own_payments.sort(key=lambda item: (str(as_date(item.get('date')) or ''), as_int(item.get('id'), 0)))
    for payment in own_payments:
        amount = money_amount(payment.get('amount'))
        recorded = InvoicePayment(
            invoice=invoice,
            date=as_date(payment.get('date')) or issue_date,
            amount=amount,
            note=payment_note(payment, modes),
        )
        recorded.save()
        stamp(InvoicePayment, recorded.pk, created_at=as_datetime(payment.get('daterecorded')))
        stats.add('invoice payments')

    created = as_datetime(row.get('datecreated'))
    sent_at = None
    if as_int(row.get('status'), 1) != INVOICE_DRAFT:
        sent_at = as_datetime(row.get('datesend')) or created
        if sent_at is None:
            sent_at = timezone.make_aware(datetime.combine(issue_date, time.min), UTC)
    stamp(Invoice, invoice.pk, sent_at=sent_at, created_at=created, updated_at=created)


def line_description(row):
    """Append the long description only when the combined text still fits."""
    short = str(row.get('description') or '').strip()
    long = str(row.get('long_description') or '').strip()
    if long:
        combined = f'{short}\n{long}' if short else long
        if len(combined) <= 255:
            return combined
    if not short:
        raise CommandError('An invoice line is missing a description.')
    if len(short) > 255:
        raise CommandError('An invoice line description is longer than 255 characters.')
    return short


def payment_note(row, modes):
    existing = str(row.get('note') or '').strip()
    mode = mode_label(row.get('paymentmode'), modes)
    transaction = str(row.get('transactionid') or '').strip()
    parts = [existing] if existing else []
    extra = [piece for piece in (mode, transaction) if piece]
    if extra:
        parts.append(' · '.join(extra))
    return '\n'.join(parts)


def mode_label(value, modes):
    if value is None:
        return ''
    text = str(value).strip()
    if not text:
        return ''
    return modes.get(text, text)


def import_salaries(salary_rows, payment_rows, currencies, users, stats):
    if not salary_rows and not payment_rows:
        return
    by_id = {str(row.get('id')): row for row in salary_rows}
    gbp_rows = []
    for row in salary_rows:
        code = currency_code(row, currencies)
        year = row_year(row)
        if code == 'GBP' and year == 2026:
            gbp_rows.append(row)
        elif code == 'USD':
            stats.skip('usd salary')
        elif code == 'GBP':
            stats.skip('salary outside 2026')
        else:
            stats.skip('other salary')

    gbp = None
    if gbp_rows:
        gbp_rows.sort(key=salary_sort_key)
        gbp = gbp_rows[-1]

    if gbp is None:
        for row in payment_rows:
            stats.skip(payment_skip_reason(payment_currency(row, by_id, currencies)))
        return

    staff_id = row_staff_id(gbp)
    user = users.get(staff_id)
    if user is None:
        raise CommandError('The GBP salary is not linked to a staff user.')
    if EmployeeSalary.objects.filter(user=user).exists():
        raise CommandError('That member already has a salary.')
    base = money_amount(row_amount(gbp))
    if base <= 0:
        raise CommandError('The GBP salary amount must be greater than zero.')
    salary = EmployeeSalary.objects.create(user=user, base_salary=base, currency='GBP')
    started = as_datetime(gbp.get('effective_date') or gbp.get('effective_from'))
    stamp(EmployeeSalary, salary.pk, created_at=started, updated_at=started)
    stats.add('salaries')

    for row in sorted(payment_rows, key=lambda item: as_int(item.get('id'), 0)):
        code = payment_currency(row, by_id, currencies)
        if code != 'GBP':
            stats.skip(payment_skip_reason(code))
            continue
        pay_staff = row_staff_id(row)
        if pay_staff and pay_staff != staff_id:
            raise CommandError('A GBP salary payment belongs to another staff member.')
        paid_on = payment_day(row)
        year, month = payment_period(row, paid_on)
        amount = money_amount(row_amount(row))
        if amount <= 0:
            raise CommandError('A salary payment amount must be greater than zero.')
        salary_month, created = SalaryMonth.objects.get_or_create(
            employee_salary=salary,
            year=year,
            month=month,
            defaults={'expected_amount': base},
        )
        if created:
            stamp(SalaryMonth, salary_month.pk, created_at=as_datetime(paid_on))
            stats.add('salary months')
        recorded = SalaryPayment.objects.create(
            salary_month=salary_month,
            amount=amount,
            payment_date=paid_on,
            payment_method='other',
            notes=row_note(row),
        )
        stamp(SalaryPayment, recorded.pk, created_at=as_datetime(paid_on))
        stats.add('salary payments')


def payment_skip_reason(code):
    if code == 'USD':
        return 'usd salary payment'
    if code == 'GBP':
        return 'gbp salary payment without salary'
    return 'other salary payment'


def payment_currency(row, salary_rows, currencies):
    code = currency_code(row, currencies)
    if code:
        return code
    for key in ('salary_id', 'staff_salary_id'):
        if key in row and row[key] not in (None, ''):
            parent = salary_rows.get(str(row[key]))
            if parent is not None:
                return currency_code(parent, currencies)
    return None


def currency_code(row, currencies):
    seen = False
    for key in ('currency_id', 'currency'):
        if key not in row:
            continue
        raw = row[key]
        if raw is None or str(raw).strip() in ('', '0', '0.0'):
            continue
        seen = True
        text = str(raw).strip()
        if len(text) == 3 and text.isalpha():
            return text.upper()
        found = currencies.get(text)
        if found is not None:
            return found.code
    if seen:
        raise CommandError('A salary row has a currency that is not in the dump.')
    return None


def row_year(row):
    for key in ('year', 'effective_year'):
        if key in row and row[key] not in (None, ''):
            return as_int(row[key])
    for key in ('effective_date', 'effective_from', 'date', 'start_date'):
        if key in row and row[key]:
            found = as_date(row[key])
            if found is not None:
                return found.year
    return None


def salary_sort_key(row):
    when = None
    for key in ('effective_date', 'effective_from', 'date', 'start_date'):
        if key in row and row[key]:
            when = as_date(row[key])
            if when is not None:
                break
    return (when or date.min, as_int(row.get('id'), 0))


def row_staff_id(row):
    for key in ('staff_id', 'staffid'):
        if key in row and row[key] not in (None, ''):
            return str(row[key])
    return None


def row_amount(row):
    for key in ('amount', 'salary', 'base_salary'):
        if key in row and row[key] not in (None, ''):
            return row[key]
    raise CommandError('A salary row has no amount.')


def payment_day(row):
    for key in ('payment_date', 'date', 'paid_at'):
        if key in row and row[key]:
            found = as_date(row[key])
            if found is not None:
                return found
    raise CommandError('A salary payment has no date.')


def payment_period(row, paid_on):
    if row.get('year') not in (None, '') and row.get('month') not in (None, ''):
        return as_int(row['year']), as_int(row['month'])
    return paid_on.year, paid_on.month


def row_note(row):
    for key in ('note', 'notes'):
        if key in row and row[key]:
            return str(row[key]).strip()
    return ''


def stamp(model, pk, **fields):
    """Write original Perfex timestamps.

    ``auto_now_add`` and ``auto_now`` replace values passed to ``create()``.
    ``QuerySet.update`` does not run those fields.
    """
    clean = {key: value for key, value in fields.items() if value is not None}
    if clean:
        model.objects.filter(pk=pk).update(**clean)


def join_address(parts):
    cleaned = []
    for part in parts:
        if part is None:
            continue
        text = str(part).strip()
        if text:
            cleaned.append(text)
    return ', '.join(cleaned)


def clip(value, limit):
    return str(value or '').strip()[:limit]


def money_amount(value):
    return Decimal(str(value)).quantize(_CENTS)


def as_decimal(value):
    if value is None or value == '':
        return None
    return Decimal(str(value))


def as_int(value, default=None):
    if value is None or value == '':
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(Decimal(str(value)))
        except (ArithmeticError, ValueError):
            return default


def id_set(value):
    return as_int(value, 0) != 0


def as_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if text in _EMPTY_DATES:
        return None
    return datetime.strptime(text[:10], '%Y-%m-%d').date()


def as_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            return value
        return timezone.make_aware(value, UTC)
    if isinstance(value, date):
        return timezone.make_aware(datetime.combine(value, time.min), UTC)
    text = str(value).strip()
    if text in _EMPTY_DATES:
        return None
    if len(text) >= 19:
        parsed = datetime.strptime(text[:19], '%Y-%m-%d %H:%M:%S')
    else:
        parsed = datetime.strptime(text[:10], '%Y-%m-%d')
    return timezone.make_aware(parsed, UTC)


def as_unix(value):
    if value is None:
        return None
    text = str(value).strip()
    if text in ('', '0', '0.0'):
        return None
    return datetime.fromtimestamp(int(Decimal(text)), tz=UTC)
