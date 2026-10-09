"""A Django email backend that sends through Resend.

Settings switch to it when ``RESEND_API_KEY`` is set, so every email the app
sends (invoices, reminders, password resets) goes the same way.
"""
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


def resend_params(message):
    """The Resend ``Emails.send`` payload for one Django ``EmailMessage``."""
    params = {
        'from': message.from_email or settings.DEFAULT_FROM_EMAIL,
        'to': list(message.to),
        'subject': message.subject,
        'text': message.body,
    }
    if message.cc:
        params['cc'] = list(message.cc)
    if message.bcc:
        params['bcc'] = list(message.bcc)
    if message.reply_to:
        params['reply_to'] = list(message.reply_to)
    if message.extra_headers:
        params['headers'] = dict(message.extra_headers)
    for content, mimetype in getattr(message, 'alternatives', []):
        if mimetype == 'text/html':
            params['html'] = content
    attachments = []
    for attachment in message.attachments:
        filename, content = attachment[0], attachment[1]
        if isinstance(content, str):
            content = content.encode()
        attachments.append({'filename': filename, 'content': list(content)})
    if attachments:
        params['attachments'] = attachments
    return params


class ResendEmailBackend(BaseEmailBackend):
    def __init__(self, api_key=None, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = api_key or settings.RESEND_API_KEY

    def send_messages(self, email_messages):
        import resend

        resend.api_key = self.api_key
        sent = 0
        for message in email_messages:
            if not message.recipients():
                continue
            try:
                resend.Emails.send(resend_params(message))
            except Exception:
                if not self.fail_silently:
                    raise
            else:
                sent += 1
        return sent
