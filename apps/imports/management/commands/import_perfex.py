import sys

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from apps.clients.models import Client
from apps.imports.parser import read_dump
from apps.imports.perfex import format_report, load_dump


class Command(BaseCommand):
    help = (
        'Import clients, projects, tasks, invoices, and the GBP salary from a Perfex SQL dump. '
        'Dry-run unless --commit is passed. Pass - to read the dump from stdin.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'dump',
            help='Path to a Perfex SQL dump, or - to read the dump from stdin.',
        )
        parser.add_argument(
            '--commit',
            action='store_true',
            help='Write the import. Without this flag the command parses, counts, and rolls back.',
        )
        parser.add_argument(
            '--admin-password',
            default='',
            help='Password for a Perfex admin that does not already have a WebFTL account.',
        )
        parser.add_argument(
            '--member-password',
            default='',
            help='Password for a Perfex member that does not already have a WebFTL account.',
        )

    def handle(self, *args, **options):
        if Client.objects.exists():
            raise CommandError('Import stopped because a client already exists.')

        dump = options['dump']
        close = False
        if dump == '-':
            stream = sys.stdin
        else:
            stream = open(dump, encoding='utf-8')
            close = True
        try:
            tables = read_dump(stream)
        finally:
            if close:
                stream.close()

        try:
            with transaction.atomic():
                if Client.objects.exists():
                    raise CommandError('Import stopped because a client already exists.')
                stats = load_dump(
                    tables,
                    admin_password=options['admin_password'],
                    member_password=options['member_password'],
                )
                self.stdout.write(format_report(stats, committed=options['commit']))
                if not options['commit']:
                    transaction.set_rollback(True)
        except (IntegrityError, ValidationError) as exc:
            raise CommandError(f'Import failed: {exc}') from exc
