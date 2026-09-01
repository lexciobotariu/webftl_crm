"""Populate a scratch database with obviously fictional demo data.

Used to produce the README screenshots without exposing any real client data.
Requires the dev dependencies (factory-boy) — it is not intended for production.
"""
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

User = get_user_model()

DEMO_PASSWORD = 'demo-password-123'
DEMO_ADMIN_EMAIL = 'ada@example.com'

CLIENTS = [
    {
        'name': 'Acme Corporation',
        'email': 'hello@acme.example',
        'phone': '+1 555 0100',
        'address': '1 Anvil Way\nCoyote Flats, AZ 85001',
    },
    {
        'name': 'Initech',
        'email': 'accounts@initech.example',
        'phone': '+1 555 0142',
        'address': '4120 Freeway Drive\nAustin, TX 78701',
    },
    {
        'name': 'Umbrella Analytics',
        'email': 'contact@umbrella-analytics.example',
        'phone': '+44 20 7946 0000',
        'address': '18 Raccoon Street\nLondon EC1A 1BB',
    },
    {
        'name': 'Hooli Labs',
        'email': 'projects@hooli-labs.example',
        'phone': '+1 555 0188',
        'address': '900 Middleout Parkway\nPalo Alto, CA 94301',
    },
    {
        'name': 'Wayne Logistics',
        'email': 'ops@wayne-logistics.example',
        'phone': '+1 555 0199',
        'address': '1007 Mountain Drive\nGotham, NJ 07001',
    },
]

TEAM = [
    ('Ada Lovelace', DEMO_ADMIN_EMAIL, 'admin'),
    ('Grace Hopper', 'grace@example.com', 'member'),
    ('Alan Turing', 'alan@example.com', 'member'),
    ('Katherine Johnson', 'katherine@example.com', 'member'),
]

PROJECTS = {
    'Acme Corporation': [
        ('Storefront Redesign', 'Rebuild the public storefront on the new design system.'),
        ('Warehouse Sync', 'Nightly inventory sync between the ERP and the storefront.'),
    ],
    'Initech': [
        ('TPS Report Automation', 'Replace the weekly spreadsheet with a scheduled report.'),
    ],
    'Umbrella Analytics': [
        ('Dashboard v2', 'Second pass at the analytics dashboard, with saved views.'),
    ],
    'Hooli Labs': [
        ('Mobile App Beta', 'Ship the iOS and Android beta to the internal test group.'),
    ],
    'Wayne Logistics': [
        ('Route Planner', 'Optimise delivery routes against live traffic data.'),
    ],
}

LABELS = [
    ('bug', '#ef4444'),
    ('feature', '#8b5cf6'),
    ('design', '#f59e0b'),
    ('infra', '#10b981'),
]

TASK_TITLES = [
    'Audit the checkout flow for accessibility',
    'Add pagination to the orders table',
    'Fix stale totals after a currency change',
    'Write migration for the new address fields',
    'Spike: background job queue options',
    'Reduce first-paint time on the landing page',
    'Handle expired sessions without a hard redirect',
    'Add retry logic to the nightly import',
    'Document the deploy runbook',
    'Trim unused indexes from the orders table',
    'Wire up the new empty states',
    'Split the settings page into sections',
    'Cache the report aggregation',
    'Add a health check endpoint',
    'Replace the ad-hoc date parsing helper',
    'Tidy up the label colour palette',
    'Add keyboard shortcuts to the board',
    'Investigate flaky upload test',
]

SUBTASKS = [
    'Write the test first',
    'Implement the happy path',
    'Handle the error case',
    'Update the docs',
]

COMMENTS = [
    'Picked this up — should be done today.',
    'Blocked on the API change landing first.',
    'Reviewed, one small comment on the naming.',
    'Confirmed on staging, looks right.',
]

TODOS = [
    'Send the Q3 invoice',
    'Book the kickoff call',
    'Renew the SSL certificate',
    'Chase the signed statement of work',
    'Write up last week’s notes',
    'Review the hosting bill',
]

NOTES = [
    ('Kickoff summary', 'Agreed on a two-week cadence. Design sign-off before each sprint.'),
    ('Access details', 'Staging is behind the VPN. Ask ops for a short-lived token.'),
    ('Billing', 'Invoices go to accounts@, net 30, PO number required on every line.'),
]


class Command(BaseCommand):
    help = 'Seed a scratch database with fictional demo data for screenshots.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Seed even if the database already contains clients.',
        )
        parser.add_argument('--seed', type=int, default=20260831, help='RNG seed.')

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            import factory  # noqa: F401
        except ImportError as exc:
            raise CommandError(
                'seed_demo_data needs the dev dependencies: pip install -r requirements-dev.txt'
            ) from exc

        from apps.accounts.factories import admin_preset, developer_preset
        from apps.clients.models import Client
        from apps.notes.models import Note
        from apps.projects.models import Project, ProjectMember
        from apps.tasks.models import Label, Subtask, Task, TaskActivity
        from apps.todos.models import Todo

        if Client.objects.exists() and not options['force']:
            raise CommandError(
                'This database already has clients. Point DATABASE_URL at a scratch '
                'database, or pass --force if you are sure.'
            )

        rng = random.Random(options['seed'])
        today = timezone.now().date()

        users = {}
        for name, email, role in TEAM:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'name': name,
                    'role': role,
                    'permission_preset': admin_preset() if role == 'admin' else developer_preset(),
                },
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=['password'])
            users[email] = user

        admin = users[DEMO_ADMIN_EMAIL]
        members = [u for u in users.values() if u != admin]

        clients = {}
        for spec in CLIENTS:
            clients[spec['name']] = Client.objects.create(**spec)

        title_pool = list(TASK_TITLES)
        rng.shuffle(title_pool)
        title_index = 0

        for client_name, project_specs in PROJECTS.items():
            client = clients[client_name]
            for project_name, description in project_specs:
                project = Project.objects.create(
                    client=client, name=project_name, description=description
                )

                for user in [admin, *rng.sample(members, k=2)]:
                    ProjectMember.objects.get_or_create(
                        project=project,
                        user=user,
                        defaults={'role': 'manager' if user == admin else 'editor'},
                    )

                labels = [
                    Label.objects.create(project=project, name=name, color=color)
                    for name, color in LABELS
                ]

                statuses = list(project.statuses.order_by('order'))
                # Weight the board so the columns look lived-in rather than uniform.
                distribution = [2, 3, 3, 2, 3]
                for status, count in zip(statuses, distribution, strict=False):
                    for order in range(count):
                        title = title_pool[title_index % len(title_pool)]
                        title_index += 1
                        task = Task.objects.create(
                            project=project,
                            status=status,
                            title=title,
                            description=(
                                'Tracked as part of the current sprint. See the linked '
                                'notes for the agreed acceptance criteria.'
                            ),
                            assignee=rng.choice([admin, *members, None]),
                            priority=rng.choice(['low', 'medium', 'high', 'urgent', '']),
                            due_date=today + timedelta(days=rng.randint(-4, 21)),
                            time_estimate=rng.choice([None, 2, 4, 8, 16]),
                            order=order,
                        )
                        task.labels.set(rng.sample(labels, k=rng.randint(0, 2)))

                        for subtask_order, subtask_title in enumerate(
                            SUBTASKS[: rng.randint(0, len(SUBTASKS))]
                        ):
                            Subtask.objects.create(
                                task=task,
                                title=subtask_title,
                                completed=subtask_order == 0,
                                order=subtask_order,
                            )

                        for comment in COMMENTS[: rng.randint(0, 3)]:
                            TaskActivity.objects.create(
                                task=task,
                                user=rng.choice([admin, *members]),
                                activity_type='comment',
                                content=comment,
                            )

                for note_title, note_body in NOTES[: rng.randint(1, len(NOTES))]:
                    Note.objects.create(
                        project=project,
                        title=note_title,
                        description=note_body,
                        created_by=admin,
                        modified_by=admin,
                    )

        for client in clients.values():
            for note_title, note_body in NOTES[:2]:
                Note.objects.create(
                    client=client,
                    title=note_title,
                    description=note_body,
                    created_by=admin,
                    modified_by=admin,
                )

        for index, todo_title in enumerate(TODOS):
            Todo.objects.create(
                owner=admin,
                client=rng.choice(list(clients.values())) if index % 2 == 0 else None,
                title=todo_title,
                description='',
                due_date=today + timedelta(days=rng.randint(-2, 14)),
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Seeded {Client.objects.count()} clients, {Project.objects.count()} projects, '
                f'{Task.objects.count()} tasks, {User.objects.count()} users.\n'
                f'Log in as {DEMO_ADMIN_EMAIL} / {DEMO_PASSWORD}'
            )
        )
