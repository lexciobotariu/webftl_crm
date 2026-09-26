from django.core.management.base import BaseCommand

from apps.tasks.services import close_expired_timers


class Command(BaseCommand):
    help = 'Close timers that have been running longer than 12 hours.'

    def handle(self, *args, **options):
        closed = close_expired_timers()
        self.stdout.write(self.style.SUCCESS(f'Closed {closed} timer(s).'))
