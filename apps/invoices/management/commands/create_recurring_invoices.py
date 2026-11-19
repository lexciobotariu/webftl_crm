from django.core.management.base import BaseCommand

from apps.invoices.recurring import create_due_invoices
from apps.tasks.recurring import create_due_tasks


class Command(BaseCommand):
    help = 'Once a day: create the draft invoices that recurring invoices have due, and the tasks of repeating tasks.'

    def handle(self, *args, **options):
        created = create_due_invoices()
        tasks = create_due_tasks()
        labels = ', '.join(invoice.number_label for invoice in created)
        self.stdout.write(self.style.SUCCESS(f'Created {len(created)} draft invoice(s).{" " + labels if labels else ""}'))
        self.stdout.write(self.style.SUCCESS(f'Repeating tasks: {len(tasks)} created.'))
