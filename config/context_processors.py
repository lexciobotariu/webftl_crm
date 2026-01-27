from pathlib import Path


def version(request):
    """Make app version available to all templates."""
    version_file = Path(__file__).resolve().parent.parent / 'VERSION'
    try:
        return {'app_version': version_file.read_text().strip()}
    except FileNotFoundError:
        return {'app_version': 'dev'}
