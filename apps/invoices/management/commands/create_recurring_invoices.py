from django.core.management.base import BaseCommand

from apps.invoices.recurring import create_due_invoices


class Command(BaseCommand):
    help = 'Create the draft invoices that recurring invoices have due today. Run once a day.'

    def handle(self, *args, **options):
        created = create_due_invoices()
        labels = ', '.join(invoice.number_label for invoice in created)
        self.stdout.write(self.style.SUCCESS(f'Created {len(created)} draft invoice(s).{" " + labels if labels else ""}'))
