# Changelog Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a changelog page that displays parsed `CHANGELOG.md` entries, accessible by clicking the version number in the sidebar.

**Architecture:** A parser function reads `CHANGELOG.md` and extracts structured version entries (version, date, sections). A view passes this data to a template. The sidebar version text becomes a link. No database, no models — the markdown file is the single source of truth.

**Tech Stack:** Django views, Django templates, Tailwind CSS, Python `re` for markdown parsing

---

## Current State

- `CHANGELOG.md` at project root, follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format
- `VERSION` file at project root, contains current version string (e.g., `0.1.2`)
- `config/context_processors.py` — reads `VERSION` file and exposes `app_version` to all templates
- `templates/components/sidebar.html:85-88` — displays `v{{ app_version }}` as plain text at bottom of sidebar
- `config/urls.py` — root URL config, includes app-specific URL files

### CHANGELOG.md format reference

```markdown
## [0.1.2] - 2026-01-29

### Fixed
- Item one
- Item two

### Changed
- Item three
```

Each version block starts with `## [x.y.z] - YYYY-MM-DD`, followed by `### Section` headers (Added, Changed, Fixed, Removed, etc.) with bullet items.

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `config/changelog.py` | Parse `CHANGELOG.md` into structured data |
| Create | `config/tests/test_changelog.py` | Tests for the parser |
| Create | `config/views.py` | Changelog view |
| Create | `templates/changelog.html` | Changelog page template |
| Modify | `config/urls.py:8` | Add changelog URL |
| Modify | `templates/components/sidebar.html:85-88` | Make version text a clickable link |

---

## Tasks

### Task 1: Create the changelog parser

**Files:**
- Create: `config/changelog.py`
- Create: `config/tests/__init__.py`
- Create: `config/tests/test_changelog.py`

- [ ] **Step 1: Write the failing tests**

Create `config/tests/__init__.py` (empty file).

Create `config/tests/test_changelog.py`:

```python
from django.test import TestCase

from config.changelog import parse_changelog


class ParseChangelogTest(TestCase):
    def test_parses_single_version(self):
        md = """# Changelog

## [0.1.0] - 2025-01-27

### Added
- Feature one
- Feature two
"""
        result = parse_changelog(md)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['version'], '0.1.0')
        self.assertEqual(result[0]['date'], '2025-01-27')
        self.assertEqual(result[0]['sections'], [
            {'name': 'Added', 'items': ['Feature one', 'Feature two']}
        ])

    def test_parses_multiple_versions(self):
        md = """# Changelog

## [0.1.2] - 2026-01-29

### Fixed
- Bug fix one

### Changed
- Refactor something

## [0.1.1] - 2026-01-27

### Changed
- Style update

## [0.1.0] - 2025-01-27

### Added
- Initial release
"""
        result = parse_changelog(md)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['version'], '0.1.2')
        self.assertEqual(result[1]['version'], '0.1.1')
        self.assertEqual(result[2]['version'], '0.1.0')
        self.assertEqual(len(result[0]['sections']), 2)
        self.assertEqual(result[0]['sections'][0]['name'], 'Fixed')
        self.assertEqual(result[0]['sections'][1]['name'], 'Changed')

    def test_empty_changelog(self):
        md = """# Changelog

All notable changes to this project will be documented in this file.
"""
        result = parse_changelog(md)
        self.assertEqual(result, [])

    def test_handles_missing_date(self):
        md = """# Changelog

## [Unreleased]

### Added
- Work in progress
"""
        result = parse_changelog(md)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['version'], 'Unreleased')
        self.assertEqual(result[0]['date'], '')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test config.tests.test_changelog -v 2`
Expected: FAIL — `ImportError: cannot import name 'parse_changelog' from 'config.changelog'`

- [ ] **Step 3: Implement the parser**

Create `config/changelog.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test config.tests.test_changelog -v 2`
Expected: ALL PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add config/changelog.py config/tests/__init__.py config/tests/test_changelog.py
git commit -m "feat: add changelog markdown parser with tests"
```

---

### Task 2: Create changelog view and URL

**Files:**
- Create: `config/views.py`
- Modify: `config/urls.py:8`
- Create: `config/tests/test_views.py`

- [ ] **Step 1: Write the failing tests**

Create `config/tests/test_views.py`:

```python
from django.test import TestCase
from django.contrib.auth import get_user_model

User = get_user_model()


class ChangelogViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='user@test.com', password='test', name='Test User', role='member'
        )

    def test_requires_login(self):
        response = self.client.get('/changelog/')
        self.assertEqual(response.status_code, 302)

    def test_returns_200_for_authenticated_user(self):
        self.client.force_login(self.user)
        response = self.client.get('/changelog/')
        self.assertEqual(response.status_code, 200)

    def test_contains_version_entries(self):
        self.client.force_login(self.user)
        response = self.client.get('/changelog/')
        # The real CHANGELOG.md has at least v0.1.0
        self.assertContains(response, '0.1.0')

    def test_uses_correct_template(self):
        self.client.force_login(self.user)
        response = self.client.get('/changelog/')
        self.assertTemplateUsed(response, 'changelog.html')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test config.tests.test_views -v 2`
Expected: FAIL — 404 (URL not found)

- [ ] **Step 3: Create the view**

Create `config/views.py`:

```python
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
```

- [ ] **Step 4: Add the URL**

In `config/urls.py`, add after line 7 (the `from` import for todo_views):

```python
from config import views as config_views
```

And add to `urlpatterns` (after `path('admin/', admin.site.urls)`):

```python
    path('changelog/', config_views.changelog_view, name='changelog'),
```

- [ ] **Step 5: Run tests — they will fail on missing template**

Run: `python manage.py test config.tests.test_views -v 2`
Expected: FAIL — `TemplateDoesNotExist: changelog.html` (for 2 tests; login redirect test passes)

- [ ] **Step 6: Commit**

```bash
git add config/views.py config/urls.py config/tests/test_views.py
git commit -m "feat: add changelog view and URL route"
```

---

### Task 3: Create changelog template

**Files:**
- Create: `templates/changelog.html`

**Design reference:** The page should follow the existing app style — dark background, zinc colors, `border-subtle`, `rounded-card` classes. Each version is a card. Section names (Added, Fixed, Changed) get color-coded badges.

- [ ] **Step 1: Create the template**

Create `templates/changelog.html`:

```html
{% extends "base.html" %}

{% block title %}Changelog - WebFTL CRM{% endblock %}

{% block full_content %}
<div class="flex-1 overflow-auto p-4">
<div class="max-w-3xl mx-auto py-8 px-4">
    <!-- Header -->
    <div class="mb-8">
        <div class="flex items-center gap-3 mb-2">
            <a href="{% url 'dashboard' %}" class="p-1 text-zinc-500 hover:text-zinc-300 hover:bg-elevated rounded transition-colors" title="Back to Dashboard">
                <i data-lucide="arrow-left" class="w-4 h-4"></i>
            </a>
            <h1 class="text-xl font-semibold text-zinc-100">Changelog</h1>
        </div>
        <p class="text-sm text-zinc-500 ml-8">All notable changes to WebFTL CRM.</p>
    </div>

    <!-- Version entries -->
    <div class="space-y-6">
        {% for entry in entries %}
        <div class="border border-border-subtle rounded-card overflow-hidden">
            <!-- Version header -->
            <div class="px-5 py-3 border-b border-border-subtle bg-panel/80">
                <div class="flex items-center justify-between">
                    <div class="flex items-center gap-2">
                        <i data-lucide="tag" class="w-4 h-4 text-zinc-500"></i>
                        <span class="text-sm font-semibold text-zinc-100">v{{ entry.version }}</span>
                    </div>
                    {% if entry.date %}
                    <span class="text-xs text-zinc-500">{{ entry.date }}</span>
                    {% endif %}
                </div>
            </div>

            <!-- Sections -->
            <div class="p-5 space-y-4">
                {% for section in entry.sections %}
                <div>
                    <span class="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-card mb-2
                        {% if section.name == 'Added' %}bg-green-500/10 text-green-400 border border-green-500/20
                        {% elif section.name == 'Fixed' %}bg-blue-500/10 text-blue-400 border border-blue-500/20
                        {% elif section.name == 'Changed' %}bg-yellow-500/10 text-yellow-400 border border-yellow-500/20
                        {% elif section.name == 'Removed' %}bg-red-500/10 text-red-400 border border-red-500/20
                        {% else %}bg-elevated text-zinc-400 border border-border-subtle
                        {% endif %}">
                        {{ section.name }}
                    </span>
                    <ul class="mt-2 space-y-1">
                        {% for item in section.items %}
                        <li class="flex items-start gap-2 text-sm text-zinc-300">
                            <span class="text-zinc-600 mt-1.5 flex-shrink-0">&bull;</span>
                            {{ item }}
                        </li>
                        {% endfor %}
                    </ul>
                </div>
                {% endfor %}
            </div>
        </div>
        {% empty %}
        <div class="flex flex-col items-center justify-center py-12 text-zinc-500">
            <i data-lucide="file-text" class="w-10 h-10 mb-3 opacity-30"></i>
            <p class="text-sm">No changelog entries found.</p>
        </div>
        {% endfor %}
    </div>
</div>
</div>
{% endblock %}
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python manage.py test config.tests -v 2`
Expected: ALL PASS (4 view tests + 4 parser tests = 8 total)

- [ ] **Step 3: Commit**

```bash
git add templates/changelog.html
git commit -m "feat: add changelog page template"
```

---

### Task 4: Make sidebar version clickable

**Files:**
- Modify: `templates/components/sidebar.html:85-88`

- [ ] **Step 1: Replace the version text with a link**

In `templates/components/sidebar.html`, replace lines 85-88:

```html
    <!-- Version -->
    <div class="px-4 py-2 border-t border-border-subtle">
        <span class="text-[11px] text-zinc-600">v{{ app_version }}</span>
    </div>
```

With:

```html
    <!-- Version -->
    <div class="px-4 py-2 border-t border-border-subtle">
        <a href="{% url 'changelog' %}" class="text-[11px] text-zinc-600 hover:text-zinc-400 transition-colors" title="View changelog">v{{ app_version }}</a>
    </div>
```

- [ ] **Step 2: Verify in browser**

1. Start the dev server: `python manage.py runserver`
2. Check: sidebar shows `v0.1.2` — now underline/hover effect on mouse over
3. Click it — navigates to `/changelog/`
4. Changelog page shows all versions (0.1.2, 0.1.1, 0.1.0) with color-coded section badges
5. Back arrow returns to dashboard

- [ ] **Step 3: Run full test suite**

Run: `python manage.py test config.tests -v 2`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add templates/components/sidebar.html
git commit -m "feat: make sidebar version link to changelog page"
```

---

## Summary of Changes

| What | Before | After |
|------|--------|-------|
| Sidebar version | Plain text `v0.1.2` | Clickable link to `/changelog/` |
| Changelog page | Doesn't exist | Full page showing all versions with color-coded sections |
| `CHANGELOG.md` | Only read by humans | Parsed and displayed in the app |

## Not In Scope

- Editing changelog from the UI
- Filtering or searching versions
- RSS/Atom feed for changelog
- Admin-only access (any authenticated user can view)
