import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestHtmxSetup:
    """What every page needs from base.html for htmx 4 (static/js/htmx-events.js does the rest)."""

    def test_htmx_4_is_loaded_pinned_and_configured(self, client, admin_user):
        client.force_login(admin_user)
        html = client.get(reverse('dashboard')).content.decode()

        assert 'https://unpkg.com/htmx.org@4.0.0/dist/htmx.min.js' in html
        assert 'integrity="sha384-BvJpBiO8Kh31EqtJe5DRIeWrHWnCGkwytKs9NKFi86Hhw96dEqdEMzZDeK9iEGTc"' in html
        # Error answers go to the toast, not into the page; Back is a real page load;
        # no 60-second cut-off (sending an invoice with its PDF can be slow).
        assert '<meta name="htmx-config" content=\'{"noSwap": [204, 304, "4xx", "5xx"], "history": "reload", "defaultTimeout": 0}\'>' in html
        # htmx's Alpine extension loads right after htmx; Alpine's own morph plugin is gone.
        assert 'https://unpkg.com/htmx.org@4.0.0/dist/ext/hx-alpine-compat.min.js' in html
        assert 'integrity="sha384-M3WRSUbYGta8wFWkcZcNj+n7cx90JkGDzvOn5M6FNsErfOjIn/9uQjzFxjFAOG5p"' in html
        assert html.index('dist/htmx.min.js') < html.index('hx-alpine-compat.min.js') < html.index('alpinejs@')
        assert '@alpinejs/morph@' not in html
        assert 'js/morph.' not in html

    def test_body_passes_csrf_spinner_and_queue_to_every_request(self, client, admin_user):
        client.force_login(admin_user)
        html = client.get(reverse('dashboard')).content.decode()
        body = html[html.index('<body'):]
        body = body[:body.index('>')]

        # htmx 4 inherits only what is marked :inherited.
        assert 'hx-headers:inherited=\'{"X-CSRFToken": "' in body
        assert 'hx-indicator:inherited="#htmx-indicator"' in body
        assert 'hx-sync:inherited="queue last"' in body
        assert 'hx-ext' not in body
