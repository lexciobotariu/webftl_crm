"""Emails the portal sends: the invite, the sign-in link, and the team's notice of an estimate answer.

The invite is logged on the client's Messages tab like every other email to the
client. Sign-in emails are not logged: they carry a working link.
"""
import logging

from django.core.mail import EmailMessage
from django.urls import reverse
from django.utils import timezone

from apps.clients.models import ClientMessage
from apps.crm.models import Company

from .access import LINK_LIFETIME, create_link

logger = logging.getLogger(__name__)


def _company():
    company = Company.load()
    return company, company.legal_name or 'WebFTL CRM'


def _send(subject, body, to, reply_to=''):
    email = EmailMessage(subject=subject, body=body, to=to)
    if reply_to:
        email.reply_to = [reply_to]
    email.send()


def send_invite(request, contact, author=None):
    """Tell the contact the portal exists and how to sign in. Returns the log entry."""
    company, name = _company()
    url = request.build_absolute_uri(reverse('portal_login')) + f'?email={contact.email}'
    subject = f'Your client portal at {name}'
    body = '\n'.join([
        f'Hello {contact.name},',
        '',
        f'You can now see your projects, invoices and estimates with {name} in our client portal.',
        '',
        f'Open {url}',
        '',
        'Enter your email address and we will send you a link to sign in. No password needed.',
        '',
        'Thank you,',
        name,
    ])
    error = ''
    try:
        _send(subject, body, [contact.email], company.email)
    except Exception as exc:
        logger.exception('Sending the portal invite to %s failed', contact.email)
        error = str(exc) or exc.__class__.__name__
    else:
        contact.portal_invited_at = timezone.now()
        contact.save(update_fields=['portal_invited_at'])
    return ClientMessage.objects.create(
        client=contact.client,
        kind=ClientMessage.EMAIL,
        subject=subject,
        body=body,
        recipients=contact.email,
        error=error,
        author=author,
    )


def send_login_links(request, contacts):
    """Email one sign-in link per contact (an email can belong to several clients)."""
    contacts = list(contacts)
    if not contacts:
        return
    company, name = _company()
    minutes = int(LINK_LIFETIME.total_seconds() // 60)
    links = []
    for contact in contacts:
        token = create_link(contact)
        if token:
            url = request.build_absolute_uri(reverse('portal_link', args=[token]))
            links.append((contact, url))
    if not links:
        return
    lines = [f'Hello {links[0][0].name},', '']
    if len(links) == 1:
        lines += ['Use this link to sign in to the client portal:', '', links[0][1]]
    else:
        lines.append('Use one of these links to sign in to the client portal:')
        for contact, url in links:
            lines += ['', f'{contact.client.name}:', url]
    lines += [
        '',
        f'The link works once, for the next {minutes} minutes.',
        'If you did not ask to sign in, you can ignore this email.',
        '',
        name,
    ]
    try:
        _send(f'Sign in to the {name} client portal', '\n'.join(lines), [links[0][0].email], company.email)
    except Exception:
        logger.exception('Sending a portal sign-in link to %s failed', links[0][0].email)


def notify_estimate_answer(request, estimate, contact, answer):
    """Log the answer on the client's Messages tab and email the company address."""
    company, _name = _company()
    verb = 'accepted' if answer == 'accepted' else 'declined'
    body = f'{contact.name} ({contact.email}) {verb} estimate {estimate.number_label} in the client portal.'
    ClientMessage.objects.create(
        client=estimate.client,
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
        _send(
            f'{estimate.client.name} {verb} estimate {estimate.number_label}',
            f'{body}\n\n{url}',
            [company.email],
        )
    except Exception:
        logger.exception('Emailing the answer to %s failed', estimate)
