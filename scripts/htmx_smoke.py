#!/usr/bin/env python
"""Click through the htmx-driven screens and report what works.

Written for the move from htmx 2 to htmx 4: run it before and after a change to
the htmx plumbing and compare. The Django tests only see the server; this sees what
the browser does with the answers (drawer opens, forms reset, toasts, CSRF, OOB
updates, history). Never point it at a real database: it edits the demo data.

    createdb webftl_demo
    export DATABASE_URL=postgres://postgres:postgres@localhost:5433/webftl_demo
    export REQUIRE_ADMIN_2FA=False   # the demo admin has no authenticator
    python manage.py migrate
    python manage.py seed_demo_data
    # gunicorn rather than runserver, so the live updates (SSE) run too:
    gunicorn config.asgi:application -k uvicorn_worker.UvicornWorker -w 2 -b 127.0.0.1:8765 &

    pip install playwright && playwright install chromium
    python scripts/htmx_smoke.py [--only drawer,comment] [--mirror DIR] [--headed]

--mirror DIR serves the CDN scripts from npm packages (``npm pack``) cached in DIR,
for machines that cannot reach unpkg/jsDelivr. Tailwind's CDN build is then replaced
by a few rules (``.hidden`` and friends), enough for the checks, not for looks.

Like take_screenshots.py, Playwright is deliberately not in requirements-dev.txt.
Exit code 1 when a check fails or the page logs an error.
"""
import argparse
import os
import re
import subprocess
import sys
import tarfile
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

BASE = os.environ.get('SMOKE_BASE', 'http://127.0.0.1:8765')
EMAIL = 'ada@example.com'
PASSWORD = 'demo-password-123'
PROJECT_PK = 1
TIMEOUT = 5000

BASE_TEMPLATE = Path(__file__).resolve().parent.parent / 'templates' / 'base.html'
# unpkg / jsDelivr: https://host/[npm/]<package>@<version>/<path>
CDN_URL = re.compile(r'https://(?:unpkg\.com|cdn\.jsdelivr\.net/npm)/((?:@[^/]+/)?[^/@]+)@([^/]+)/(.+)')
ICONIFY_URL = re.compile(r'https://code\.iconify\.design/iconify-icon/([^/]+)/(.+)')
TAILWIND_STUB = """
(() => {
  const style = document.createElement('style');
  style.textContent = '.hidden{display:none!important}.flex{display:flex}.block{display:block}'
    + '.inline-flex{display:inline-flex}.fixed{position:fixed}.absolute{position:absolute}.relative{position:relative}';
  document.head.appendChild(style);
  window.tailwind = { config: {} };
})();
"""


# --- CDN mirror -------------------------------------------------------------------

def mirror_file(cache, package, version, path):
    folder = cache / f"{package.replace('/', '__')}@{version}"
    if not folder.exists():
        folder.mkdir(parents=True)
        subprocess.run(['npm', 'pack', f'{package}@{version}', '--silent'], cwd=folder,
                       check=True, capture_output=True)
        archive = next(folder.glob('*.tgz'))
        with tarfile.open(archive) as tar:
            tar.extractall(folder, filter='data')
    return (folder / 'package' / path).read_bytes()


def warm_mirror(cache):
    """Fetch every CDN package base.html names, so no page waits for npm."""
    for url in re.findall(r'src="(https://[^"]+)"', BASE_TEMPLATE.read_text()):
        match = CDN_URL.match(url)
        if match:
            mirror_file(cache, *match.groups())
        match = ICONIFY_URL.match(url)
        if match:
            mirror_file(cache, 'iconify-icon', match.group(1), 'dist/' + match.group(2))


def install_mirror(context, cache):
    cache.mkdir(parents=True, exist_ok=True)
    warm_mirror(cache)

    def handle(route):
        url = route.request.url
        if url.startswith('https://cdn.tailwindcss.com'):
            return route.fulfill(body=TAILWIND_STUB, content_type='text/javascript')
        match = CDN_URL.match(url)
        if match:
            package, version, path = match.groups()
        else:
            match = ICONIFY_URL.match(url)
            if not match:
                return route.abort()
            package, version, path = 'iconify-icon', match.group(1), 'dist/' + match.group(2)
        try:
            body = mirror_file(cache, package, version, path)
        except (subprocess.CalledProcessError, FileNotFoundError, StopIteration):
            return route.abort()
        return route.fulfill(body=body, content_type='text/javascript',
                             headers={'Access-Control-Allow-Origin': '*'})

    context.route(re.compile(r'https://(unpkg\.com|cdn\.jsdelivr\.net|code\.iconify\.design|cdn\.tailwindcss\.com)/.*'),
                  handle)


# --- Helpers ----------------------------------------------------------------------

class CheckFailed(Exception):
    pass


def expect(condition, message):
    if not condition:
        raise CheckFailed(message)


def htmx_version(page):
    return page.evaluate('window.htmx && htmx.version')


def wait_idle(page, ms=300):
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(ms)


def open_list(page):
    page.goto(f'{BASE}/projects/{PROJECT_PK}/tasks/?layout=list&group=status')
    page.wait_for_selector('[data-task-row]')
    wait_idle(page)


def open_first_task(page):
    """Click the first row; returns its pk once the drawer shows the task."""
    open_list(page)
    row = page.locator('[data-task-row]').first
    pk = row.get_attribute('id').replace('task-', '')
    row.locator('span').nth(1).click()
    page.wait_for_selector(f'#slide-over:not(.hidden) #task-title-{pk}', timeout=TIMEOUT)
    wait_idle(page)
    return pk


def tap(locator):
    """Click through the DOM. The drawer slides and re-renders icons, so Playwright's
    "stable element" wait can time out although a person could click just fine."""
    locator.first.wait_for(state='attached')
    locator.first.evaluate('el => el.click()')


def error_toast_text(page):
    toast = page.locator('#htmx-error-toast')
    return toast.text_content() if toast.is_visible() else ''


# --- Checks -----------------------------------------------------------------------
# Each takes the page and raises CheckFailed (or a Playwright timeout) when broken.

def check_drawer_opens(page):
    """A list row opens the task drawer (openSlideOver after the swap)."""
    open_first_task(page)


def check_new_task_drawer(page):
    """The New task button opens the create drawer (data-after-success="open-drawer")."""
    open_list(page)
    page.click('#task-new')
    page.wait_for_selector('#slide-over:not(.hidden) form', timeout=TIMEOUT)


def check_drawer_edit_csrf(page):
    """An edit in the drawer is a POST: it needs the CSRF header from <body>."""
    pk = open_first_task(page)
    drawer = page.locator('#slide-over')
    tap(drawer.locator(f'#priority-value-{pk} button'))
    with page.expect_response(lambda r: f'/tasks/{pk}/' in r.url and r.request.method == 'POST') as info:
        tap(drawer.locator(f'#priority-value-{pk} [hx-post]').nth(1))
    expect(info.value.status == 200, f'priority POST answered {info.value.status}')
    wait_idle(page)
    expect(not error_toast_text(page), f'error toast: {error_toast_text(page)}')


def check_global_indicator(page):
    """The global spinner shows while a request runs (hx-indicator on <body>)."""
    pk = open_first_task(page)
    seen = {'on': False}

    def slow(route):
        seen['on'] = page.evaluate(
            "document.getElementById('htmx-indicator').classList.contains('htmx-request')")
        route.continue_()

    page.route(re.compile(rf'.*/tasks/{pk}/.*priority.*'), slow)
    drawer = page.locator('#slide-over')
    tap(drawer.locator(f'#priority-value-{pk} button'))
    tap(drawer.locator(f'#priority-value-{pk} [hx-post]').nth(2))
    wait_idle(page)
    page.unroute(re.compile(rf'.*/tasks/{pk}/.*priority.*'))
    expect(seen['on'], '#htmx-indicator did not get htmx-request during the request')


def check_description_preview(page):
    """Description editor: Preview is rendered by the server (fetch with the CSRF token)."""
    pk = open_first_task(page)
    tap(page.locator(f'#task-description-{pk} [hx-get]'))
    page.wait_for_selector(f'#task-description-{pk} textarea', timeout=TIMEOUT)
    page.fill(f'#task-description-{pk} textarea', 'Smoke **bold** text')
    with page.expect_response(lambda r: 'preview' in r.url) as info:
        tap(page.locator(f'#task-description-{pk} button:has-text("Preview")'))
    expect(info.value.status == 200, f'preview answered {info.value.status}')
    page.wait_for_selector(f'#task-description-{pk} strong:has-text("bold")', timeout=TIMEOUT)


def check_comment_resets(page):
    """A new comment appears and the form empties (data-after-success="reset")."""
    pk = open_first_task(page)
    box = page.locator('#slide-over textarea[name="content"]')
    text = f'Smoke comment {int(time.time())}'
    box.fill(text)
    with page.expect_response(lambda r: '/comment' in r.url and r.request.method == 'POST') as info:
        tap(box.locator('xpath=ancestor::form').locator('button[type=submit]'))
    expect(info.value.status == 200, f'comment POST answered {info.value.status}')
    page.wait_for_selector(f'#activity-items-{pk} :text("{text}")', timeout=TIMEOUT)
    wait_idle(page)
    expect(box.input_value() == '', 'comment box was not emptied after sending')


def check_subtask_add_and_counter(page):
    """Adding a sub-task appends it, hides and resets the form, and updates the OOB counter."""
    pk = open_first_task(page)
    counter_before = page.locator(f'#subtask-counter-{pk}').text_content()
    form = page.locator(f'#subtask-form-{pk}')
    page.evaluate(f"document.getElementById('subtask-form-{pk}').classList.remove('hidden')")
    title = f'Smoke sub-task {int(time.time())}'
    form.locator('input[name=title]').fill(title)
    with page.expect_response(lambda r: 'subtask' in r.url and r.request.method == 'POST') as info:
        tap(form.locator('button[type=submit]'))
    expect(info.value.status == 200, f'sub-task POST answered {info.value.status}')
    page.wait_for_selector(f'#subtask-list-{pk} :text("{title}")', timeout=TIMEOUT)
    wait_idle(page)
    expect('hidden' in (form.get_attribute('class') or ''), 'sub-task form stayed open')
    expect(form.locator('input[name=title]').input_value() == '', 'sub-task form was not reset')
    expect(page.locator(f'#subtask-counter-{pk}').text_content() != counter_before,
           'sub-task counter (OOB) did not change')


def check_subtask_reorder(page):
    """Reorder as x-sort does it (htmx.ajax with an ids array); the order is saved."""
    pk = open_first_task(page)
    ids = page.eval_on_selector_all(f'#subtask-list-{pk} [data-subtask]', 'els => els.map(e => e.dataset.subtask)')
    if len(ids) < 2:
        for n in range(2):
            page.evaluate(f"document.getElementById('subtask-form-{pk}').classList.remove('hidden')")
            page.fill(f'#subtask-form-{pk} input[name=title]', f'Order {n}')
            tap(page.locator(f'#subtask-form-{pk} button[type=submit]'))
            wait_idle(page)
        ids = page.eval_on_selector_all(f'#subtask-list-{pk} [data-subtask]', 'els => els.map(e => e.dataset.subtask)')
    wanted = list(reversed(ids))
    with page.expect_response(lambda r: 'reorder' in r.url) as info:
        page.evaluate(
            "([pk, ids]) => htmx.ajax('POST', `/tasks/${pk}/subtasks/reorder/`, "
            "{source: document.getElementById(`subtask-list-${pk}`), swap: 'none', values: {ids}})",
            [pk, wanted])
    expect(info.value.status == 204, f'reorder answered {info.value.status}')
    open_first_task(page)
    now = page.eval_on_selector_all(f'#subtask-list-{pk} [data-subtask]', 'els => els.map(e => e.dataset.subtask)')
    expect(now == wanted, f'order not saved: wanted {wanted}, got {now}')


def check_error_toast(page):
    """A 4xx answer shows its message in the toast and is not swapped into the page."""
    pk = open_first_task(page)
    item = page.locator(f'#subtask-list-{pk} [data-subtask]').first
    if not item.count():
        raise CheckFailed('no sub-task to rename (run the sub-task check first)')
    sid = item.get_attribute('data-subtask')
    tap(item.locator('button[title=Rename]'))
    field = page.locator(f'#subtask-{sid} input[name=title]')
    page.evaluate(f"document.querySelector('#subtask-{sid} input[name=title]').removeAttribute('required')")
    field.fill('')
    with page.expect_response(lambda r: 'rename' in r.url) as info:
        field.press('Enter')
    expect(info.value.status == 400, f'empty rename answered {info.value.status}')
    page.wait_for_selector('#htmx-error-toast:not(.hidden)', timeout=TIMEOUT)
    expect(page.locator(f'#subtask-{sid}').count() == 1, 'the error replaced the sub-task row')


def check_toolbar_view(page):
    """The toolbar changes the view in place and the URL follows."""
    open_list(page)
    with page.expect_response(lambda r: 'group=priority' in r.url):
        page.evaluate("""() => {
            const form = document.getElementById('task-toolbar');
            const field = form.querySelector('[name=group]') || Object.assign(document.createElement('input'), {type: 'hidden', name: 'group'});
            field.value = 'priority';
            form.appendChild(field);
            htmx.trigger(form, 'submit');
        }""")
    wait_idle(page)
    expect('group=priority' in page.url, f'URL did not follow the toolbar: {page.url}')
    page.wait_for_selector('[data-task-row]')


def check_history_back(page):
    """Back after a toolbar change shows the earlier view, scripts not doubled."""
    check_toolbar_view(page)
    page.go_back()
    wait_idle(page, 600)
    expect('group=status' in page.url, f'Back landed on {page.url}')
    page.wait_for_selector('[data-task-row]')
    count = page.evaluate("document.querySelectorAll('#task-view-refresh').length")
    expect(count == 1, f'{count} copies of #task-view-refresh after Back')


def check_quick_edit_row(page):
    """Quick edit on a row: the menu POST and the single-row refresh."""
    open_list(page)
    row = page.locator('[data-task-row]').first
    rid = row.get_attribute('id')
    row.locator('[data-quick=priority]').click()
    page.wait_for_selector('#task-quick-menu:not([hidden]) [role=menuitem], #task-quick-menu:not([hidden]) button',
                           timeout=TIMEOUT)
    with page.expect_response(lambda r: r.request.method == 'POST') as info:
        page.locator('#task-quick-menu button').nth(1).click()
    expect(info.value.status == 200, f'quick edit answered {info.value.status}')
    wait_idle(page)
    expect(page.locator(f'#{rid}').count() == 1, 'row missing after quick edit')


def check_board(page):
    """The board renders and a card opens the drawer."""
    page.goto(f'{BASE}/projects/{PROJECT_PK}/tasks/?layout=board')
    card = page.locator('[data-task-row] [onclick]').first
    card.wait_for(timeout=TIMEOUT)
    tap(card)
    page.wait_for_selector('#slide-over:not(.hidden) [id^=task-title-]', timeout=TIMEOUT)


def check_palette(page):
    """Ctrl+K search shows results; Enter opens the task in the drawer."""
    open_list(page)
    page.keyboard.press('Control+k')
    page.wait_for_selector('#palette:not([hidden])', timeout=TIMEOUT)
    word = page.locator('[data-task-row]').first.get_attribute('data-identifier')
    page.keyboard.type(word)
    page.wait_for_selector('#palette-results [id^=palette-task-]', timeout=TIMEOUT)
    page.keyboard.press('Enter')
    page.wait_for_selector('#slide-over:not(.hidden) [id^=task-title-]', timeout=TIMEOUT)


def check_close_drawer_events(page):
    """Deleting a task from the drawer closes it and refreshes the list (HX-Trigger order)."""
    pk = open_first_task(page)
    page.once('dialog', lambda dialog: dialog.accept())
    with page.expect_response(lambda r: '/delete/' in r.url) as info:
        tap(page.locator(f'#slide-over [hx-post$="/tasks/{pk}/delete/"]'))
    expect(info.value.status == 200, f'delete answered {info.value.status}')
    page.wait_for_selector('#slide-over.hidden', state='attached', timeout=TIMEOUT)
    wait_idle(page, 600)
    expect(page.locator(f'#task-{pk}').count() == 0, 'deleted task still in the list')


def check_client_todos(page):
    """My to-dos: Show completed toggles the list (hx-vals sends show_completed)."""
    page.goto(f'{BASE}/tasks/my/todos/')
    toggle = page.locator('[data-show-completed]').first
    toggle.wait_for(timeout=TIMEOUT)
    before = toggle.get_attribute('data-show-completed')
    with page.expect_response(lambda r: '/todos' in r.url and r.request.method == 'GET') as info:
        toggle.click()
    expect(info.value.status == 200, f'to-dos answered {info.value.status}')
    expect(('show_completed=true' in info.value.url) == (before == 'false'),
           f'toggle asked for {info.value.url}')


def check_todo_drawer(page):
    """Add to-do opens the drawer (data-after-success="open-drawer", no script in the answer)."""
    page.goto(f'{BASE}/tasks/my/todos/')
    button = page.locator('button[hx-get$="/todos/create/"]').first
    button.wait_for(timeout=TIMEOUT)
    tap(button)
    page.wait_for_selector('#slide-over:not(.hidden) form', timeout=TIMEOUT)


def check_label_create(page):
    """Project settings: a new label is added and the form empties (data-after-success="reset")."""
    page.goto(f'{BASE}/projects/{PROJECT_PK}/settings/')
    field = page.locator('form[hx-post$="/labels/create/"] input[name=name], form[hx-post*="label"] input[name=name]').first
    field.wait_for(timeout=TIMEOUT)
    name = f'Smoke {int(time.time())}'
    field.fill(name)
    with page.expect_response(lambda r: 'label' in r.url and r.request.method == 'POST') as info:
        tap(field.locator('xpath=ancestor::form').locator('button[type=submit]'))
    expect(info.value.status == 200, f'label POST answered {info.value.status}')
    page.wait_for_selector(f':text("{name}")', timeout=TIMEOUT)
    wait_idle(page)
    expect(field.input_value() == '', 'label form was not reset')


def check_time_log(page):
    """Log time from the drawer: the popover form resets and closes (Alpine @request:end)."""
    open_first_task(page)
    drawer = page.locator('#slide-over')
    tap(drawer.locator('button:has-text("Log time")'))
    form = drawer.locator('form[hx-post*="time"]').filter(has=page.locator('input[name=duration]')).first
    form.locator('input[name=duration]').fill('15m')
    with page.expect_response(lambda r: 'time' in r.url and r.request.method == 'POST') as info:
        tap(form.locator('button[type=submit]'))
    expect(info.value.status == 200, f'log time answered {info.value.status}')
    wait_idle(page)
    expect(form.locator('input[name=duration]').input_value() == '', 'Log time form was not reset')
    expect(not form.is_visible(), 'Log time popover stayed open')


def check_inbox(page):
    """Inbox: J opens the next notification in the pane; a slower answer for another one is dropped."""
    page.goto(f'{BASE}/inbox/')
    rows = page.locator('[data-notification]')
    try:
        rows.first.wait_for(timeout=2000)
    except PlaywrightTimeout as exc:
        raise CheckFailed('no notifications for the demo admin (comment on one of their tasks as someone else)') from exc
    if rows.count() < 2:
        raise CheckFailed('needs at least two notifications')
    page.locator('#inbox-list').focus()
    page.keyboard.press('j')
    # attached, not visible: under --mirror the stub CSS has no lg:flex for the pane.
    page.wait_for_selector('#inbox-pane [data-pane-for]', state='attached', timeout=TIMEOUT)
    first = page.locator('#inbox-pane [data-pane-for]').first.get_attribute('data-pane-for')
    page.keyboard.press('j')
    page.keyboard.press('j')
    wait_idle(page, 600)
    shown = page.locator('#inbox-pane [data-pane-for]').first.get_attribute('data-pane-for')
    selected = page.locator('#inbox').get_attribute('data-selected')
    expect(shown == selected, f'pane shows {shown}, selection is {selected}')
    expect(shown != first, 'J did not move on')


def check_live_update(page, context):
    """A change made in another tab reaches this one through SSE and updates the row."""
    open_list(page)
    other = context.new_page()
    other.goto(page.url)
    other.wait_for_selector('[data-task-row]')
    rid = page.locator('[data-task-row]').first.get_attribute('id')
    pk = rid.replace('task-', '')
    page.wait_for_timeout(1500)  # the stream connects
    title = f'Live {int(time.time())}'
    other.evaluate(
        "([pk, title]) => htmx.ajax('POST', `/tasks/${pk}/title/`, {target: 'body', swap: 'none', values: {title}})",
        [pk, title])
    try:
        page.wait_for_selector(f'#{rid}:has-text("{title}")', timeout=8000)
    finally:
        other.close()



def check_create_more(page):
    """Create more: the drawer stays open on a fresh form; the hidden Preview panel stays hidden."""
    open_list(page)
    page.click('#task-new')
    form = page.locator('#slide-over:not(.hidden) form')
    form.wait_for(timeout=TIMEOUT)
    more = form.locator('input[name=create_more]')
    if not more.is_checked():
        tap(more)
    title = f'More {int(time.time())}'
    form.locator('input[name=title]').fill(title)
    tap(form.locator('button[type=submit]'))
    page.wait_for_selector(f'#slide-over:not(.hidden) [role=status]:has-text("{title}")', timeout=TIMEOUT)
    wait_idle(page)
    expect(page.locator('#slide-over input[name=title]').input_value() == '', 'title not cleared')
    preview = page.locator('#task-form-description-preview')
    expect(preview.count() == 1 and not preview.is_visible(), 'Preview panel visible after Create more')
    tap(page.locator('#slide-over input[name=create_more]'))  # leave the choice off for the next run
    page.evaluate("localStorage.removeItem('taskCreateMore')")


def check_tab_id(page):
    """Every htmx request names this tab (X-Tab-Id), so live updates skip their own tab."""
    pk = open_first_task(page)
    drawer = page.locator('#slide-over')
    tap(drawer.locator(f'#priority-value-{pk} button'))
    with page.expect_request(lambda r: f'/tasks/{pk}/' in r.url and r.method == 'POST') as info:
        tap(drawer.locator(f'#priority-value-{pk} [hx-post]').nth(2))
    headers = info.value.headers
    expect(headers.get('x-tab-id'), 'no X-Tab-Id header')
    expect(headers.get('x-csrftoken'), 'no X-CSRFToken header')


def check_autosave_latest(page):
    """Invoice editor: three quick changes to one line save the last value (hx-sync queue last)."""
    page.goto(f'{BASE}/invoices/')
    tap(page.locator('[hx-get$="/invoices/create/"]'))
    form = page.locator('#slide-over:not(.hidden) form')
    form.wait_for(timeout=TIMEOUT)
    client = form.locator('select[name=client] option:not([value=""])').first.get_attribute('value')
    form.locator('select[name=client]').select_option(client)
    tap(form.locator('button[type=submit]'))
    try:
        page.wait_for_selector('#doc-lines', timeout=TIMEOUT)
    except PlaywrightTimeout:
        raise CheckFailed('no invoice created (the first client in the list needs a currency)') from None
    url = page.url
    page.fill('#new-line-description', 'Autosave check')
    page.fill('#new-line input[name=unit_price]', '10')
    page.press('#new-line-description', 'Enter')
    page.wait_for_selector('#doc-lines tr[id^="line-"]:not(#new-line)', timeout=TIMEOUT)
    wait_idle(page)
    line = page.locator('#doc-lines tr[id^="line-"]:not(#new-line)').first
    page.route(re.compile(r'.*/lines/\d+/.*'), lambda route: (time.sleep(0.4), route.continue_()))
    for value in ('2', '3', '4'):
        line.locator('input[name=quantity]').evaluate(
            "(el, v) => { el.value = v; el.dispatchEvent(new Event('change', {bubbles: true})); }", value)
    page.unroute(re.compile(r'.*/lines/\d+/.*'))
    wait_idle(page, 1500)
    page.goto(url)
    saved = page.locator('#doc-lines tr[id^="line-"]:not(#new-line) input[name=quantity]').first.input_value()
    try:
        expect(float(saved) == 4, f'quantity saved as {saved}, typed 4 last')
    finally:
        page.once('dialog', lambda dialog: dialog.accept())  # "Delete INV-…?"
        page.evaluate("() => { const b = document.querySelector('[hx-post$=\"/delete/\"][hx-confirm^=\"Delete\"]'); if (b) b.click(); }")
        wait_idle(page)


CHECKS = [
    ('drawer', check_drawer_opens),
    ('new-task', check_new_task_drawer),
    ('csrf', check_drawer_edit_csrf),
    ('indicator', check_global_indicator),
    ('preview', check_description_preview),
    ('comment', check_comment_resets),
    ('subtask', check_subtask_add_and_counter),
    ('reorder', check_subtask_reorder),
    ('error-toast', check_error_toast),
    ('toolbar', check_toolbar_view),
    ('history', check_history_back),
    ('quick-edit', check_quick_edit_row),
    ('board', check_board),
    ('palette', check_palette),
    ('todos', check_client_todos),
    ('todo-drawer', check_todo_drawer),
    ('label', check_label_create),
    ('time-log', check_time_log),
    ('inbox', check_inbox),
    ('create-more', check_create_more),
    ('tab-id', check_tab_id),
    ('autosave', check_autosave_latest),
    ('live', check_live_update),
    ('delete', check_close_drawer_events),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--only', help='comma-separated check names')
    parser.add_argument('--mirror', type=Path, help='serve CDN scripts from npm packages cached here')
    parser.add_argument('--headed', action='store_true')
    parser.add_argument('--chromium', help='path to a Chromium binary')
    args = parser.parse_args()
    wanted = set(args.only.split(',')) if args.only else None

    results = []
    with sync_playwright() as playwright:
        launch = {'headless': not args.headed}
        if args.chromium:
            launch['executable_path'] = args.chromium
        browser = playwright.chromium.launch(**launch)
        context = browser.new_context(viewport={'width': 1400, 'height': 900})
        context.set_default_timeout(TIMEOUT)
        if args.mirror:
            install_mirror(context, args.mirror)
        page = context.new_page()
        errors = []
        page.on('console', lambda m: errors.append(f'console {m.type}: {m.text}')
                if m.type == 'error' and 'favicon' not in m.text else None)
        page.on('pageerror', lambda e: errors.append(f'pageerror: {e}'))

        page.goto(f'{BASE}/accounts/login/')
        page.fill("input[name='login']", EMAIL)
        page.fill("input[name='password']", PASSWORD)
        page.click("button[type='submit']")
        page.wait_for_url(f'{BASE}/')
        print(f'htmx {htmx_version(page)} at {BASE}\n')

        for name, check in CHECKS:
            if wanted and name not in wanted:
                continue
            errors.clear()
            try:
                if name == 'live':
                    check(page, context)
                else:
                    check(page)
                problem = None
            except (CheckFailed, PlaywrightTimeout) as exc:
                lines = str(exc).splitlines()
                detail = [line.strip() for line in lines[1:] if 'intercepts' in line or 'waiting for' in line]
                problem = ' | '.join([lines[0], *detail[:2]])[:400]
            # 4xx answers the check provoked on purpose are logged by the browser too.
            page_errors = [e for e in errors if 'status of 4' not in e and 'Error Code 4' not in e]
            # htmx 2 logs a request it aborted itself (hx-sync replace, the inbox's quick J J)
            # as htmx:afterRequest + htmx:sendAbort. A network failure still shows as sendError.
            page_errors = [e for e in page_errors if 'htmx:afterRequest' not in e and 'htmx:sendAbort' not in e]
            # htmx 4 logs the same as htmx:error with an AbortError.
            page_errors = [e for e in page_errors if not ('htmx:error' in e and 'AbortError' in e)]
            if args.mirror:
                # Other hosts (icon and font APIs) are unreachable on such machines.
                page_errors = [e for e in page_errors if 'Failed to load resource: net::ERR_' not in e]
            if not problem and page_errors:
                problem = page_errors[0]
            results.append((name, problem))
            print(f"  {'ok  ' if not problem else 'FAIL'} {name:12} {check.__doc__.strip().splitlines()[0]}")
            if problem:
                print(f'       -> {problem}')
        browser.close()

    failed = [name for name, problem in results if problem]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed" + (f"; failed: {', '.join(failed)}" if failed else ''))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
