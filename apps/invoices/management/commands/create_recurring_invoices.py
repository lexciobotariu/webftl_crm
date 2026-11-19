from django.core.management.base import BaseCommand

from apps.invoices.recurring import create_due_invoices
from apps.services.core import run_daily
from apps.tasks.recurring import create_due_tasks


class Command(BaseCommand):
    help = (
        'Once a day: renew or end services, create the draft invoices that recurring invoices '
        'have due, and the tasks that recurring tasks have due.'
    )

    def handle(self, *args, **options):
        # Renewals and paused services first, so a service ended today gets no new draft.
        services = run_daily()
        created = create_due_invoices()
        tasks = create_due_tasks()
        labels = ', '.join(invoice.number_label for invoice in created)
        self.stdout.write(self.style.SUCCESS(f'Created {len(created)} draft invoice(s).{" " + labels if labels else ""}'))
        self.stdout.write(self.style.SUCCESS(
            f'Recurring tasks: {len(tasks)} created. '
            f'Services: {len(services["renewed"])} renewed, {len(services["ended"])} ended.'
        ))
