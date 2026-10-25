from django.conf import settings


class AlwaysHttpsMiddleware:
    """Treat every request as HTTPS when the site is only ever reached over HTTPS.

    Behind Dokploy's proxy (and any CDN in front of it) the forwarded scheme
    header can say http even though visitors use https, so links built from
    the request (the Claude connector address, OAuth metadata, portal emails)
    came out as http://. With ALWAYS_HTTPS the scheme no longer depends on it.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.ALWAYS_HTTPS:
            request.META['wsgi.url_scheme'] = 'https'
            request.META['SERVER_PORT'] = '443'
            header = settings.SECURE_PROXY_SSL_HEADER
            if header:
                request.META[header[0]] = header[1]
        return self.get_response(request)
