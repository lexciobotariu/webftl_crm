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

    function selectedRow() {
        return selectedId ? document.getElementById(selectedId) : null;
    }

    function updatePosition() {
        const label = pane() && pane().querySelector('[data-inbox-position]');
        if (!label) return;
        const index = rows().findIndex((row) => row.id === selectedId);
        label.textContent = index < 0 ? '' : `${index + 1} / ${list().dataset.total}`;
    }

    function markSelected() {
        if (!list()) return;
        rows().forEach((row) => row.setAttribute('aria-selected', row.id === selectedId ? 'true' : 'false'));
        const row = selectedRow();
        if (row) {
            list().setAttribute('aria-activedescendant', row.id);
            row.scrollIntoView({ block: 'nearest' });
        } else {
            list().removeAttribute('aria-activedescendant');
        }
        updatePosition();
    }

    function select(row) {
        selectedId = row.id;
        root().dataset.selected = row.id.replace('notification-', '');
        markSelected();
    }

    function open(row) {
        if (!row) return;
        select(row);
        htmx.ajax('POST', row.getAttribute('hx-post'), { target: '#inbox-pane', swap: 'innerHTML' });
        list().focus({ preventScroll: true });
    }

    function clearPane() {
        selectedId = null;
        delete root().dataset.selected;
        const empty = document.getElementById('inbox-pane-empty');
        if (empty) pane().replaceChildren(empty.content.cloneNode(true));
        if (window.lucide) lucide.createIcons();
        markSelected();
        history.replaceState(history.state, '', `?show=${encodeURIComponent(show())}`);
        list().focus({ preventScroll: true });
    }

    function move(delta) {
        const all = rows();
        let index = all.findIndex((row) => row.id === selectedId);
        if (index < 0) index = delta > 0 ? -1 : all.length;
        const next = all[index + delta];
        if (next) {
            open(next);
        } else if (delta > 0 && document.getElementById('inbox-more')) {
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
        if (url) htmx.ajax('POST', withShow(url), { target: '#inbox-pane', swap: 'none' });
    }

    function removeEmptyDays() {
        list().querySelectorAll('[data-day]').forEach((day) => {
            if (!day.querySelector('[data-notification]')) day.remove();
        });
    }

    function deleteSelected() {
        const row = selectedRow();
        if (!row) return;
        const all = rows();
        const index = all.indexOf(row);
        // Like archiving a mail: the next one opens, or the one above at the end.
        const next = all[index + 1] || all[index - 1] || null;
        htmx.ajax('POST', withShow(row.dataset.deleteUrl), { target: '#inbox-pane', swap: 'none' }).then(() => {
            if (document.getElementById(row.id)) return; // refused: nothing changed
            list().dataset.total = String(Math.max(0, Number(list().dataset.total) - 1));
            removeEmptyDays();
            if (next && document.getElementById(next.id)) open(document.getElementById(next.id));
            else clearPane();
        });
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
        else if (key === 'Enter' && inList && event.target.closest('[data-notification]') === null) open(selectedRow() || rows()[0]);
        else if (key === 'e' || key === 'E') toggleRead();
        else if ((key === 'Backspace' || key === 'Delete') && selectedId) deleteSelected();
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
        if (row && !event.ctrlKey && !event.metaKey && !event.shiftKey) select(row);
        if (help() && (event.target === help() || event.target.closest('[data-shortcuts-close]'))) hideHelp();
    });

    document.addEventListener('htmx:afterSwap', (event) => {
        if (!root()) return;
        if (event.detail.target === pane()) {
            highlightActivity();
            updatePosition();
        }
    });

    document.addEventListener('htmx:afterSettle', () => {
        if (!root()) return;
        markSelected();
        if (openAfterMore) {
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
            clearPane();
        }
    });

    document.addEventListener('DOMContentLoaded', () => {
        if (!root()) return;
        if (root().dataset.selected) {
            selectedId = `notification-${root().dataset.selected}`;
            markSelected();
            highlightActivity();
        }
        window.registerEscLayer('help', hideHelp);
        window.registerEscLayer('selection', () => {
            if (!selectedId) return false;
            clearPane();
            return true;
        });
    });
})();
