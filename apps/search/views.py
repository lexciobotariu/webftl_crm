from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.template.loader import render_to_string

from . import services


@login_required
def search(request):
    """The results the command palette shows for ``?q=``.

    Rendered without the request: this is a list of links, and the context
    processors would add queries to every keystroke for nothing.
    """
    results = services.search(request.user, request.GET.get('q'))
    return HttpResponse(render_to_string('search/results.html', {'results': results}))
