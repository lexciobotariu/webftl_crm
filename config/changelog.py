import re


def parse_changelog(content):
    """
    Parse Keep a Changelog formatted markdown into structured data.

    Returns a list of dicts:
    [
        {
            'version': '0.1.2',
            'date': '2026-01-29',
            'sections': [
                {'name': 'Fixed', 'items': ['Bug fix one', 'Bug fix two']},
                {'name': 'Changed', 'items': ['Refactor something']},
            ]
        },
        ...
    ]
    """
    entries = []
    current_entry = None
    current_section = None

    for line in content.splitlines():
        # Match version header: ## [0.1.2] - 2026-01-29  or  ## [Unreleased]
        version_match = re.match(r'^## \[(.+?)\](?:\s*-\s*(\S+))?', line)
        if version_match:
            current_entry = {
                'version': version_match.group(1),
                'date': version_match.group(2) or '',
                'sections': [],
            }
            entries.append(current_entry)
            current_section = None
            continue

        if current_entry is None:
            continue

        # Match section header: ### Added, ### Fixed, etc.
        section_match = re.match(r'^### (.+)', line)
        if section_match:
            current_section = {
                'name': section_match.group(1).strip(),
                'items': [],
            }
            current_entry['sections'].append(current_section)
            continue

        # Match list item: - Some change
        item_match = re.match(r'^- (.+)', line)
        if item_match and current_section is not None:
            current_section['items'].append(item_match.group(1).strip())

    return entries
