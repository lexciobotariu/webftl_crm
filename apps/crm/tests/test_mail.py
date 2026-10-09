"""The Resend email backend and how its settings are read (release 0.28.0)."""
from unittest import mock

from django.core.mail import EmailMultiAlternatives
from django.test import override_settings

from apps.crm.mail import ResendEmailBackend, resend_params
from config.settings import env_value


def test_quotes_around_env_values_are_optional(monkeypatch):
    for raw in ('WebFTL <facturi@x.ro>', '"WebFTL <facturi@x.ro>"', "'WebFTL <facturi@x.ro>'", ' "WebFTL <facturi@x.ro>" '):
        monkeypatch.setenv('DEFAULT_FROM_EMAIL', raw)
        assert env_value('DEFAULT_FROM_EMAIL') == 'WebFTL <facturi@x.ro>'
    monkeypatch.setenv('DEFAULT_FROM_EMAIL', '"')
    assert env_value('DEFAULT_FROM_EMAIL') == '"'


@override_settings(DEFAULT_FROM_EMAIL='WebFTL <facturi@x.ro>')
def test_a_django_message_maps_to_the_resend_payload():
    message = EmailMultiAlternatives('Invoice', 'Plain', to=['a@client.test'], cc=['b@client.test'],
                                     reply_to=['office@agency.test'])
    message.attach_alternative('<p>Html</p>', 'text/html')
    message.attach('INV-0001.pdf', b'%PDF', 'application/pdf')

    params = resend_params(message)
    assert params['from'] == 'WebFTL <facturi@x.ro>'
    assert params['to'] == ['a@client.test']
    assert params['cc'] == ['b@client.test']
    assert params['reply_to'] == ['office@agency.test']
    assert (params['text'], params['html']) == ('Plain', '<p>Html</p>')
    assert params['attachments'] == [{'filename': 'INV-0001.pdf', 'content': list(b'%PDF')}]
    assert 'bcc' not in params


def test_the_backend_sends_with_the_key_and_raises_on_failure():
    message = EmailMultiAlternatives('Hi', 'Body', 'from@x.ro', to=['a@client.test'])
    with mock.patch('resend.Emails.send') as send:
        assert ResendEmailBackend(api_key='re_test').send_messages([message]) == 1
    import resend

    assert resend.api_key == 're_test'
    assert send.call_args.args[0]['subject'] == 'Hi'

    with mock.patch('resend.Emails.send', side_effect=RuntimeError('rejected')):
        try:
            ResendEmailBackend(api_key='re_test').send_messages([message])
        except RuntimeError as exc:
            assert str(exc) == 'rejected'
        else:
            raise AssertionError('expected the failure to surface')
        assert ResendEmailBackend(api_key='re_test', fail_silently=True).send_messages([message]) == 0
