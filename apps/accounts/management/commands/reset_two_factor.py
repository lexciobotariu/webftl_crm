from allauth.mfa.models import Authenticator
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        'Remove the authenticator app and recovery codes of one person, for when '
        'they lost both. They sign in with the password and set it up again.'
    )

    def add_arguments(self, parser):
        parser.add_argument('email')

    def handle(self, *args, email, **options):
        user = get_user_model().objects.filter(email__iexact=email.strip()).first()
        if user is None:
            raise CommandError(f'No one signs in as {email}.')
        deleted, _ = Authenticator.objects.filter(user=user).delete()
        if deleted:
            self.stdout.write(f'Two-factor sign-in removed for {user.email}.')
        else:
            self.stdout.write(f'{user.email} had no two-factor sign-in.')
