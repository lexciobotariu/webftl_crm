from django.core.management.base import BaseCommand

from apps.invoices.recurring import create_due_invoices
from apps.maintenance.services import run_daily


class Command(BaseCommand):
    help = (
        'Create the draft invoices that recurring invoices have due today, then the maintenance '
        'checks tasks and renewals. Run once a day.'
    )

    def handle(self, *args, **options):
        # Renewals and paused plans first, so a plan ended today gets no new draft.
        maintenance = run_daily()
        created = create_due_invoices()
        labels = ', '.join(invoice.number_label for invoice in created)
        self.stdout.write(self.style.SUCCESS(f'Created {len(created)} draft invoice(s).{" " + labels if labels else ""}'))
        self.stdout.write(self.style.SUCCESS(
            f'Maintenance: {len(maintenance["checks"])} checks task(s), '
            f'{len(maintenance["renewed"])} plan(s) renewed, {len(maintenance["ended"])} ended.'
        ))
