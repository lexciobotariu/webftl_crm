#!/usr/bin/env python
"""Regenerate the README screenshots from seeded demo data.

Never point this at a real database — the screenshots would leak client data.

    createdb webftl_demo
    export DATABASE_URL=postgres://postgres:postgres@localhost:5433/webftl_demo
    python manage.py migrate
    python manage.py seed_demo_data
    python manage.py runserver 8765 --noreload &

    pip install playwright && playwright install chromium
    python scripts/take_screenshots.py

Playwright is deliberately not in requirements-dev.txt: CI does not need it, and
it pulls in browser binaries.
"""
import sys

from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8765'
EMAIL = 'ada@example.com'
PASSWORD = 'demo-password-123'
OUT = 'screenshots'

# seed_demo_data is deterministic, so these ids are stable.
CLIENT_PK = 1
PROJECT_PK = 1
TASK_PK = 13  # has sub-tasks, comments and a label, so the detail views look real

# 1016x536 at DPR 2 reproduces the 2032x1072 images already in the README.
VIEWPORT = {'width': 1016, 'height': 536}
SCALE = 2


def main():
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport=VIEWPORT, device_scale_factor=SCALE)
        page = context.new_page()
        page.on(
            'console',
            lambda m: errors.append(f'{m.type}: {m.text}')
            if m.type == 'error' and 'favicon' not in m.text
            else None,
        )
        page.on('pageerror', lambda e: errors.append(f'pageerror: {e}'))

        page.goto(f'{BASE}/accounts/login/')
        page.fill("input[name='login']", EMAIL)
        page.fill("input[name='password']", PASSWORD)
        page.click("button[type='submit']")
        page.wait_for_url(f'{BASE}/')

        def shot(name, url, before=None, settle=0):
            page.goto(f'{BASE}{url}')
            page.wait_for_load_state('networkidle')
            if before:
                before()
            page.wait_for_timeout(settle + 400)
            page.screenshot(path=f'{OUT}/{name}.png')
            print(f'  {name}.png  <- {url}')

        shot('dashboard', '/')
        shot('client-detail', f'/clients/{CLIENT_PK}/')
        shot('project-overview', f'/projects/{PROJECT_PK}/overview/')
        shot('task-list', f'/projects/{PROJECT_PK}/tasks/')
        shot('kanban-board', f'/projects/{PROJECT_PK}/kanban/')

        def open_task_drawer():
            page.evaluate(
                "pk => htmx.ajax('GET', `/tasks/${pk}/`, "
                "{target: '#slide-over', swap: 'innerHTML'})",
                TASK_PK,
            )
            page.wait_for_selector('#slide-over:not(.hidden)', timeout=5000)

        shot('task-detail-sidebar', f'/projects/{PROJECT_PK}/kanban/',
             before=open_task_drawer, settle=800)
        shot('task-detail-fullpage', f'/tasks/project/{PROJECT_PK}/{TASK_PK}/')

        browser.close()

    if errors:
        print('\nconsole errors:', file=sys.stderr)
        for error in errors:
            print(' ', error, file=sys.stderr)
        return 1
    print('\nno console errors')
    return 0


if __name__ == '__main__':
    sys.exit(main())
