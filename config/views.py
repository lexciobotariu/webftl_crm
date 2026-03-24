from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .changelog import parse_changelog


@login_required
def changelog_view(request):
    """Display parsed changelog entries."""
    changelog_path = Path(__file__).resolve().parent.parent / 'CHANGELOG.md'
    try:
        content = changelog_path.read_text()
    except FileNotFoundError:
        content = ''

    entries = parse_changelog(content)

    return render(request, 'changelog.html', {
        'entries': entries,
    })
