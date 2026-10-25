from .bus import origin_tab


class OriginTabMiddleware:
    """Remembers which browser tab sent the request (header ``X-Tab-Id``), so the
    change it makes is not sent back to that same tab."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = origin_tab.set(clean_tab(request.headers.get('X-Tab-Id', '')))
        try:
            return self.get_response(request)
        finally:
            origin_tab.reset(token)


def clean_tab(value):
    """A tab id is what the browser makes with crypto.randomUUID(); anything else is dropped."""
    value = (value or '')[:64]
    return value if value and all(c.isalnum() or c == '-' for c in value) else ''
