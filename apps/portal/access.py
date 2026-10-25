"""Who may use the client portal, and how they sign in.

A contact signs in with a magic link: they type their email, get a link that
works once and for 15 minutes, and opening it keeps them signed in for 30 days
in that browser. The portal never uses the staff login. Its session is a
separate signed cookie holding the contact and the email it was issued for, so
unticking "Portal access", archiving the client or changing the contact's email
ends it at the next request.
"""
import hashlib
import secrets
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.shortcuts import redirect
from django.utils import timezone

from apps.clients.models import ClientContact

from .models import PortalLink

LINK_LIFETIME = timedelta(minutes=15)
SESSION_LIFETIME = timedelta(days=30)
# Links one contact can be sent in an hour, so the form cannot be used to flood an inbox.
LINKS_PER_HOUR = 5

COOKIE_NAME = 'portal_session'
COOKIE_SALT = 'apps.portal.session'


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def portal_contacts():
    """Contacts that may sign in: ticked, with an email, at a client that is not archived."""
    return (
        ClientContact.objects.filter(portal_access=True, client__archived_at__isnull=True)
        .exclude(email='')
        .select_related('client')
    )


def contacts_for_email(email):
    return portal_contacts().filter(email__iexact=email.strip())


def create_link(contact, now=None):
    """A new sign-in token for ``contact``, or None when it has had too many this hour."""
    now = now or timezone.now()
    recent = PortalLink.objects.filter(contact=contact, created_at__gte=now - timedelta(hours=1)).count()
    if recent >= LINKS_PER_HOUR:
        return None
    token = secrets.token_urlsafe(32)
    PortalLink.objects.create(contact=contact, token_hash=_hash(token), expires_at=now + LINK_LIFETIME)
    return token


def find_link(token):
    """The unused, unexpired link for ``token`` whose contact still has access, or None."""
    link = (
        PortalLink.objects.filter(token_hash=_hash(token), contact__in=portal_contacts())
        .select_related('contact__client')
        .first()
    )
    return link if link and link.usable else None


def use_link(token):
    """Spend the link and return its contact, or None when it cannot be used."""
    with transaction.atomic():
        link = (
            PortalLink.objects.select_for_update()
            .filter(token_hash=_hash(token), contact__in=portal_contacts())
            .first()
        )
        if link is None or not link.usable:
            return None
        now = timezone.now()
        link.used_at = now
        link.save(update_fields=['used_at'])
        contact = link.contact
        contact.portal_last_login_at = now
        contact.save(update_fields=['portal_last_login_at'])
        return contact


def _cookie_value(contact):
    return f'{contact.pk}:{contact.email.lower()}'


def sign_in(response, contact):
    response.set_signed_cookie(
        COOKIE_NAME,
        _cookie_value(contact),
        salt=COOKIE_SALT,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite='Lax',
    )


def sign_out(response):
    response.delete_cookie(COOKIE_NAME, samesite='Lax')


def current_contact(request):
    """The signed-in contact, or None."""
    try:
        value = request.get_signed_cookie(
            COOKIE_NAME, salt=COOKIE_SALT, max_age=SESSION_LIFETIME.total_seconds(),
        )
    except (KeyError, signing.BadSignature):
        return None
    pk, _, email = value.partition(':')
    if not pk.isdigit():
        return None
    contact = portal_contacts().filter(pk=int(pk)).first()
    if contact is None or contact.email.lower() != email:
        return None
    return contact


def portal_login_required(view):
    """Sets ``request.portal_contact`` and ``request.portal_client``, or sends the visitor to sign in."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        contact = current_contact(request)
        if contact is None:
            return redirect('portal_login')
        request.portal_contact = contact
        request.portal_client = contact.client
        return view(request, *args, **kwargs)
    return wrapped
