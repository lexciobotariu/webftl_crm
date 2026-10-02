// The unread badge on the sidebar's Inbox link. No polling: it asks the server again
// when the tab becomes visible and when a response says notifications changed
// (HX-Trigger: notificationsChanged, after one or all are marked read).
(function () {
    function refresh() {
        const badge = document.querySelector('[data-inbox-badge]');
        if (!badge) return;
        fetch(badge.dataset.countUrl, { credentials: 'same-origin', redirect: 'error' })
            .then((response) => (response.ok ? response.text() : null))
            .then((text) => {
                const count = parseInt(text, 10);
                if (Number.isNaN(count)) return;
                badge.textContent = String(count);
                badge.setAttribute('aria-label', `${count} unread`);
                badge.hidden = count === 0;
            })
            .catch(() => {});
    }

    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') refresh();
    });
    document.addEventListener('notificationsChanged', refresh);
})();

// The Inbox page (templates/notifications/inbox.html): a mail-like column of
// notifications on the left and the open one on the right. Moving with J / K opens
// what you land on, which marks it read, as in a mail client. Selection lives here
// (aria-selected on the rows), so the server never has to know it; the address keeps
// ?n=<pk> in step with replaceState, so moving does not fill the history.
(function () {
    const root = () => document.getElementById('inbox');
    const list = () => document.getElementById('inbox-list');
    const pane = () => document.getElementById('inbox-pane');
    const help = () => document.getElementById('task-shortcuts');
    const rows = () => Array.from(list() ? list().querySelectorAll('[data-notification]') : []);
    const show = () => (root() && root().dataset.show) || 'all';
    let selectedId = null;
    let openAfterMore = false;
    // An "open" that was overtaken by the next one still marked its notification read
    // on the server, but its row update was thrown away; the list is refreshed once
    // the pane settles.
    let staleRows = false;
    let deleting = false;

    // Text being written in the pane (a reply, a description, a comment being edited).
    function hasDraft() {
        if (!pane()) return false;
        return Array.from(pane().querySelectorAll('textarea')).some((field) => field.value.trim() && field.value !== field.defaultValue);
    }

    // Replacing the pane throws that text away, whatever has the focus: ask first.
    function mayLeavePane() {
        return !hasDraft() || window.confirm('Discard the text you were writing?');
    }

    function refreshList() {
        const selected = root().dataset.selected || '';
        const url = `${list().dataset.refreshUrl}&list=1&n=${encodeURIComponent(selected)}`;
        htmx.ajax('GET', url, { target: '#inbox-list', select: '#inbox-list', swap: 'outerHTML' }).catch(() => {});
    }

    // After a failed open the pane still shows the notification from before; the
    // selection goes back to it, so the pane's buttons act on what is on screen.
    function syncSelectionToPane() {
        const shown = pane() && pane().querySelector('[data-pane-for]');
        const row = shown && document.getElementById(`notification-${shown.dataset.paneFor}`);
        if (row) {
            selectedId = row.id;
            root().dataset.selected = shown.dataset.paneFor;
        } else {
            selectedId = null;
            delete root().dataset.selected;
        }
        markSelected(false);
    }

    function selectedRow() {
        return selectedId ? document.getElementById(selectedId) : null;
    }

    function updatePosition() {
        const label = pane() && pane().querySelector('[data-inbox-position]');
        if (!label) return;
        const index = rows().findIndex((row) => row.id === selectedId);
        label.textContent = index < 0 ? '' : `${index + 1} / ${list().dataset.total}`;
    }

    // ``scroll`` only when the selection itself moved: a refresh after an edit in the
    // pane must not pull the list away from where the person is scrolling.
    function markSelected(scroll) {
        if (!list()) return;
        rows().forEach((row) => row.setAttribute('aria-selected', row.id === selectedId ? 'true' : 'false'));
        const row = selectedRow();
        if (row) {
            list().setAttribute('aria-activedescendant', row.id);
            if (scroll) row.scrollIntoView({ block: 'nearest' });
        } else {
            list().removeAttribute('aria-activedescendant');
        }
        updatePosition();
    }

    function select(row) {
        selectedId = row.id;
        root().dataset.selected = row.id.replace('notification-', '');
        markSelected(true);
    }

    // Requests go out from #inbox-opener, whose hx-sync="this:replace" aborts the one
    // still in flight: pressing J twice quickly must end on the second notification.
    function open(row) {
        if (!row || !mayLeavePane()) return;
        select(row);
        // An aborted request (superseded by the next J) rejects; its row needs a refresh.
        htmx.ajax('POST', row.dataset.openUrl, { source: '#inbox-opener', target: '#inbox-pane', swap: 'innerHTML' })
            .catch(() => { staleRows = true; });
        list().focus({ preventScroll: true });
    }

    function clearPane(force) {
        if (!force && !mayLeavePane()) return false;
        selectedId = null;
        delete root().dataset.selected;
        const empty = document.getElementById('inbox-pane-empty');
        if (empty) pane().replaceChildren(empty.content.cloneNode(true));
        if (window.lucide) lucide.createIcons();
        markSelected(false);
        history.replaceState(history.state, '', `?show=${encodeURIComponent(show())}`);
        list().focus({ preventScroll: true });
        return true;
    }

    function move(delta) {
        const all = rows();
        let index = all.findIndex((row) => row.id === selectedId);
        if (index < 0) index = delta > 0 ? -1 : all.length;
        const next = all[index + delta];
        if (next) {
            open(next);
        } else if (delta > 0 && document.getElementById('inbox-more') && !openAfterMore) {
            // At the end of what is loaded: load the next page, then keep going.
            openAfterMore = true;
            document.getElementById('inbox-more').click();
        }
    }

    function withShow(url) {
        return `${url}?show=${encodeURIComponent(show())}`;
    }

    function toggleRead() {
        const row = selectedRow();
        if (!row) return;
        let url = null;
        if (row.dataset.unread === '1') url = row.dataset.readUrl;
        else if (row.dataset.canUnread === '1') url = row.dataset.unreadUrl;
        // Not targeted at the pane: even a swap of "none" fires afterSwap on its target,
        // which would scroll the pane back to the comment on every toggle.
        if (url) htmx.ajax('POST', withShow(url), { target: '#inbox-opener', swap: 'none' }).catch(() => {});
    }

    function removeEmptyDays() {
        list().querySelectorAll('[data-day]').forEach((day) => {
            if (!day.querySelector('[data-notification]')) day.remove();
        });
    }

    function deleteSelected() {
        const row = selectedRow();
        // One at a time: a second press before the answer would delete the next one too.
        if (!row || deleting || !mayLeavePane()) return;
        deleting = true;
        const all = rows();
        const index = all.indexOf(row);
        // Like archiving a mail: the next one opens, or the one above at the end.
        const next = all[index + 1] || all[index - 1] || null;
        htmx.ajax('POST', withShow(row.dataset.deleteUrl), { target: '#inbox-opener', swap: 'none' }).then(() => {
            if (document.getElementById(row.id)) return; // refused: nothing changed
            list().dataset.total = String(Math.max(0, Number(list().dataset.total) - 1));
            removeEmptyDays();
            // The draft question was already answered above.
            pane().querySelectorAll('textarea').forEach((field) => { field.value = field.defaultValue; });
            if (next && document.getElementById(next.id)) open(document.getElementById(next.id));
            else clearPane(true);
            // The last one gone: let the server draw the empty state and the totals.
            if (!rows().length) refreshList();
        }).catch(() => {}).finally(() => { deleting = false; });
    }

    // The comment that raised the notification: bring it into view and light it up.
    function highlightActivity() {
        const holder = pane() && pane().querySelector('[data-activity]');
        if (!holder) return;
        const item = pane().querySelector(`#activity-${holder.dataset.activity}`);
        if (!item) return;
        item.scrollIntoView({ block: 'center' });
        item.classList.add('inbox-flash');
        setTimeout(() => item.classList.remove('inbox-flash'), 1600);
    }

    function showHelp() {
        if (!help()) return;
        help().hidden = false;
        help().querySelector('[role="dialog"]').focus();
    }

    function hideHelp() {
        if (!help() || help().hidden) return false;
        help().hidden = true;
        list().focus({ preventScroll: true });
        return true;
    }

    const typing = (target) => !!(target.closest && target.closest('input, textarea, select, [contenteditable=""], [contenteditable="true"]'));
    const blocked = () => {
        const palette = document.getElementById('palette');
        const drawer = document.getElementById('slide-over');
        return (palette && !palette.hidden) || (drawer && !drawer.classList.contains('hidden'));
    };

    document.addEventListener('keydown', (event) => {
        if (!root() || event.defaultPrevented || event.isComposing || event.keyCode === 229) return;
        if (event.ctrlKey || event.metaKey || event.altKey || typing(event.target) || blocked()) return;
        if (help() && !help().hidden) return;
        const inList = event.target === document.body || (list() && list().contains(event.target));
        const key = event.key;
        let handled = true;
        if (key === 'j' || (key === 'ArrowDown' && inList)) move(1);
        else if (key === 'k' || (key === 'ArrowUp' && inList)) move(-1);
        // Enter on a focused control ("Show more", a row link) is that control's own click.
        else if (key === 'Enter' && inList && !event.target.closest('a, button')) open(selectedRow() || rows()[0]);
        else if (key === 'e' || key === 'E') toggleRead();
        // Only from the list: Backspace on a button in the pane must not delete anything.
        // Not on auto-repeat: a held key would delete one notification after another.
        else if ((key === 'Backspace' || key === 'Delete') && selectedId && inList) { if (!event.repeat) deleteSelected(); }
        else if (key === '?') showHelp();
        else handled = false;
        if (handled) event.preventDefault();
    });

    document.addEventListener('click', (event) => {
        if (!root()) return;
        const action = event.target.closest('[data-inbox-action]');
        if (action) {
            const name = action.dataset.inboxAction;
            if (name === 'help') showHelp();
            else if (name === 'close') clearPane();
            else if (name === 'prev') move(-1);
            else if (name === 'next') move(1);
            else if (name === 'toggle') toggleRead();
            else if (name === 'delete') deleteSelected();
            return;
        }
        const row = event.target.closest('[data-notification]');
        // A modified click keeps the link's own behaviour (a new tab through ?n=).
        if (row && !event.ctrlKey && !event.metaKey && !event.shiftKey && event.button === 0) {
            event.preventDefault();
            open(row);
        }
        if (help() && (event.target === help() || event.target.closest('[data-shortcuts-close]'))) hideHelp();
    });

    // A slower answer for a notification that is no longer selected is not shown.
    document.addEventListener('htmx:beforeSwap', (event) => {
        if (!root() || event.detail.target !== pane()) return;
        const match = /data-pane-for="(\d+)"/.exec(event.detail.serverResponse || '');
        if (match && `notification-${match[1]}` !== selectedId) event.detail.shouldSwap = false;
    });

    document.addEventListener('htmx:afterSwap', (event) => {
        if (!root()) return;
        // The pane itself, not the out-of-band row and count that ride along.
        if (event.target === pane()) {
            highlightActivity();
            updatePosition();
            if (staleRows) {
                staleRows = false;
                refreshList();
            }
        }
    });

    // An open that failed (the notification is gone, the server erred, no network)
    // leaves the pane as it was; so does a "Show more" that failed.
    ['htmx:responseError', 'htmx:sendError'].forEach((name) => {
        document.addEventListener(name, (event) => {
            if (!root()) return;
            const elt = event.detail.elt;
            if (elt && elt.id === 'inbox-opener') syncSelectionToPane();
            if (elt && elt.id === 'inbox-more') openAfterMore = false;
        });
    });

    document.addEventListener('htmx:afterSettle', (event) => {
        if (!root()) return;
        markSelected(false);
        // Only the answer to "Show more" carries on to the next row; another refresh of
        // the list settling in between must not open anything.
        const source = event.detail.requestConfig && event.detail.requestConfig.elt;
        if (openAfterMore && event.target.id === 'inbox-list' && source && source.id === 'inbox-more') {
            openAfterMore = false;
            move(1);
        }
    });

    // A task deleted from the pane takes its notifications with it.
    document.addEventListener('htmx:afterRequest', (event) => {
        if (!root() || !event.detail.successful) return;
        const elt = event.detail.elt;
        if (elt && pane().contains(elt) && /\/tasks\/\d+\/delete\/$/.test(event.detail.requestConfig.path)) {
            // Its response also sends taskStatusChanged, which refreshes the list.
            clearPane(true);
        }
    });

    document.addEventListener('DOMContentLoaded', () => {
        if (!root()) return;
        if (root().dataset.selected) {
            selectedId = `notification-${root().dataset.selected}`;
            markSelected(true);
            highlightActivity();
        }
        window.registerEscLayer('help', hideHelp);
        // Not while typing: Esc in a comment being written leaves the draft alone.
        window.registerEscLayer('selection', (event) => {
            if (!selectedId || (event && typing(event.target))) return false;
            // Handled either way: a draft the person chose to keep keeps the pane open.
            clearPane();
            return true;
        });
    });
})();
