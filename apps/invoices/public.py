"""The online page of an estimate: a secret link anyone who has it can open, no account needed.

The link is ``/e/<pk>/<token>/``, where the token is an HMAC (with SECRET_KEY)
of the estimate's ``public_key``. A copy of the database cannot open it, a new
key revokes it, and it only works once the estimate has been sent. The person
reading it accepts by typing their name and ticking a box; that name, the time
and their IP address are stored on the estimate, whose lines are already locked.
"""
import logging
import secrets

from django.core.mail import EmailMessage
from django.db import transaction
from django.urls import reverse
from django.utils.crypto import constant_time_compare, salted_hmac

from apps.clients.models import ClientMessage
from apps.crm.models import Company

from .models import Estimate

logger = logging.getLogger(__name__)

SALT = 'apps.invoices.public.estimate'


def _token(estimate):
    return salted_hmac(SALT, f'{estimate.pk}:{estimate.public_key}').hexdigest()[:32]


def ensure_key(estimate):
    """Give the estimate a link key if it has none. Returns the estimate."""
    if not estimate.public_key:
        with transaction.atomic():
            locked = Estimate.objects.select_for_update().get(pk=estimate.pk)
            if not locked.public_key:
                locked.public_key = secrets.token_hex(16)
                locked.save(update_fields=['public_key', 'updated_at'])
            estimate.public_key = locked.public_key
    return estimate


def reset_key(estimate):
    """A new key: the old link stops working."""
    estimate.public_key = secrets.token_hex(16)
    estimate.save(update_fields=['public_key', 'updated_at'])
    return estimate


def public_path(estimate):
    ensure_key(estimate)
    return reverse('estimate_public', args=[estimate.pk, _token(estimate)])


def public_url(request, estimate):
    return request.build_absolute_uri(public_path(estimate))


def find(pk, token):
    """The estimate this link opens, or None: wrong token, no key, or still a draft."""
    estimate = (
        Estimate.objects.select_related('client', 'lead', 'project')
        .prefetch_related('lines')
        .filter(pk=pk, sent_at__isnull=False)
        .exclude(public_key='')
        .first()
    )
    if estimate is None or not constant_time_compare(_token(estimate), token or ''):
        return None
    return estimate


def client_ip(request):
    """The visitor's address. Behind Traefik the first X-Forwarded-For entry is the visitor."""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    address = forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR', '')
    return address or None


def notify_answer(request, estimate, answer, name, where='on the online page'):
    """Log the answer on the client's or lead's messages and email the company address."""
    company = Company.load()
    verb = 'accepted' if answer == 'accepted' else 'declined'
    who = name or 'Someone'
    body = f'{who} {verb} estimate {estimate.number_label} {where}.'
    ClientMessage.objects.create(
        client=estimate.client,
        lead=estimate.lead,
        kind=ClientMessage.NOTE,
        subject=f'Estimate {estimate.number_label} {verb}',
        body=body,
        estimate=estimate,
        project=estimate.project,
    )
    if not company.email:
        return
    url = request.build_absolute_uri(reverse('estimate_detail', args=[estimate.pk]))
    try:
        email = EmailMessage(
            subject=f'{estimate.recipient_name} {verb} estimate {estimate.number_label}',
            body=f'{body}\n\n{url}',
            to=[company.email],
        )
        email.send()
    except Exception:
        logger.exception('Emailing the answer to %s failed', estimate)
