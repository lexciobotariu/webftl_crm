// The Tasks page and My Tasks: the quick-edit menu on rows and cards, and scroll
// that survives a refresh of #task-view. One menu element (#task-quick-menu) serves
// every row; a delegated listener opens it from any [data-quick] button.
(function () {
    if (window.__taskViewLoaded) return;
    window.__taskViewLoaded = true;

    const menu = () => document.getElementById('task-quick-menu');
    const LABELS = { priority: 'Set priority', status: 'Set status', assignee: 'Set assignee' };
    let state = null; // the open menu: { trigger, kind, pk, rowId, token, top, left }
    let token = 0;
    let refocus = null; // after a refresh replaces the trigger, put focus back on its twin

    function endpoint(name, pk, extra) {
        return menu().dataset[name].replace('/0/', '/' + pk + '/').replace('FIELD', extra || '');
    }

    function priorityItems(current) {
        const fragment = document.getElementById('task-quick-priority').content.cloneNode(true);
        fragment.querySelectorAll('[role="menuitemradio"]').forEach((item) => {
            const checked = item.dataset.value === current;
            item.setAttribute('aria-checked', checked ? 'true' : 'false');
            item.querySelector('[data-check]').hidden = !checked;
        });
        return fragment;
    }

    function items() {
        return Array.from(menu().querySelectorAll('[role="menuitemradio"]'));
    }

    function focusItem(item) {
        if (item) item.focus({ preventScroll: true });
    }

    function position() {
        const m = menu();
        const rect = state.trigger.getBoundingClientRect();
        const gap = 4;
        const pad = 8;
        const width = m.offsetWidth;
        const height = m.offsetHeight;
        const left = Math.min(Math.max(pad, rect.left), window.innerWidth - width - pad);
        let top = rect.bottom + gap;
        if (top + height > window.innerHeight - pad) {
            const above = rect.top - gap - height;
            top = above >= pad ? above : Math.max(pad, window.innerHeight - height - pad);
        }
        m.style.left = left + 'px';
        m.style.top = top + 'px';
    }

    function showItems() {
        position();
        const list = items();
        focusItem(list.find((item) => item.getAttribute('aria-checked') === 'true') || list[0]);
    }

    function closeMenu(returnFocus) {
        if (!state) return;
        const { trigger, kind, rowId } = state;
        const m = menu();
        state = null;
        token += 1;
        m.hidden = true;
        m.replaceChildren();
        trigger.setAttribute('aria-expanded', 'false');
        if (!returnFocus) return;
        if (trigger.isConnected) trigger.focus({ preventScroll: true });
        // A refresh replaces the trigger; its twin in the new list takes the focus.
        refocus = { trigger, rowId, kind };
        // If no refresh follows, don't let a much later swap pull focus back.
        setTimeout(() => { if (refocus && refocus.rowId === rowId) refocus = null; }, 4000);
    }

    function openMenu(trigger) {
        if (state && state.trigger === trigger) {
            closeMenu(true);
            return;
        }
        closeMenu(false);
        // The drawer and the menu would compete for the same screen.
        if (window.closeSlideOver) window.closeSlideOver();
        const row = trigger.closest('[data-task-row]');
        if (!row) return;
        const kind = trigger.dataset.quick;
        const mine = ++token;
        const at = trigger.getBoundingClientRect();
        state = { trigger, kind, pk: row.id.replace('task-', ''), rowId: row.id, token: mine, top: at.top, left: at.left };
        trigger.setAttribute('aria-expanded', 'true');
        const m = menu();
        m.setAttribute('aria-label', LABELS[kind]);
        m.hidden = false;
        if (kind === 'priority') {
            m.replaceChildren(priorityItems(trigger.dataset.current || ''));
            showItems();
            return;
        }
        m.innerHTML = '<div class="px-3 py-2 text-xs text-zinc-500">Loading…</div>';
        position();
        fetch(endpoint('quickUrl', state.pk, kind), { credentials: 'same-origin' })
            .then((response) => {
                if (!response.ok) throw new Error('quick menu ' + response.status);
                return response.text();
            })
            .then((html) => {
                if (!state || state.token !== mine) return;
                m.innerHTML = html;
                showItems();
            })
            .catch(() => {
                if (!state || state.token !== mine) return;
                closeMenu(true);
                window.showErrorToast('Could not load the options. Try again.');
            });
    }

    function choose(item) {
        const { kind, pk } = state;
        const value = item.dataset.value;
        const unchanged = item.getAttribute('aria-checked') === 'true';
        closeMenu(true);
        if (unchanged) return;
        const field = { priority: 'priority', status: 'status_id', assignee: 'assignee_id' }[kind];
        // The menu is the source, so the HX-Trigger events reach body even though
        // the button that was pressed is gone by the time the response arrives.
        htmx.ajax('POST', endpoint(kind + 'Url', pk), {
            source: '#task-quick-menu',
            target: '#task-quick-menu',
            swap: 'none',
            values: { [field]: value },
        });
    }

    document.addEventListener('click', (event) => {
        const trigger = event.target.closest('[data-quick]');
        if (trigger) {
            event.preventDefault();
            openMenu(trigger);
            return;
        }
        if (state && !menu().contains(event.target)) closeMenu(false);
    });

    document.addEventListener('DOMContentLoaded', () => {
        menu().addEventListener('click', (event) => {
            const item = event.target.closest('[role="menuitemradio"]');
            if (item && state) choose(item);
        });
        menu().addEventListener('keydown', (event) => {
            const list = items();
            const at = list.indexOf(document.activeElement);
            let next = null;
            if (event.key === 'ArrowDown') next = list[(at + 1) % list.length];
            else if (event.key === 'ArrowUp') next = list[(at - 1 + list.length) % list.length];
            else if (event.key === 'Home') next = list[0];
            else if (event.key === 'End') next = list[list.length - 1];
            else if (event.key === 'Tab') closeMenu(true);
            if (next) {
                event.preventDefault();
                focusItem(next);
            }
        });
    });

    // Scrolling that moves the trigger would leave the menu floating, so close then.
    // A scroll that leaves it where it was (an event queued from before the menu
    // opened, a scroll in another pane) is not a reason to close.
    document.addEventListener('scroll', (event) => {
        if (!state || menu().contains(event.target)) return;
        const rect = state.trigger.getBoundingClientRect();
        if (!state.trigger.isConnected || Math.abs(rect.top - state.top) > 1 || Math.abs(rect.left - state.left) > 1) {
            closeMenu(false);
        }
    }, true);
    window.addEventListener('resize', () => closeMenu(false));
    window.registerEscLayer('menu', () => {
        if (!state) return false;
        closeMenu(true);
        return true;
    });

    // --- Scroll that survives a refresh -------------------------------------
    // A refresh replaces #task-view; without this every edit would send the list
    // back to the top. Elements opt in with data-keep-scroll="<key>".
    let scrolls = null;

    function isRefresh(detail) {
        const source = detail.requestConfig && detail.requestConfig.elt;
        return !!source && (source.id === 'task-view-refresh' || source.id === 'task-more');
    }

    document.body.addEventListener('htmx:beforeSwap', (event) => {
        const target = event.detail.target;
        if (!target || target.id !== 'task-view' || !isRefresh(event.detail)) return;
        scrolls = {};
        const kept = [target, ...target.querySelectorAll('[data-keep-scroll]')];
        kept.forEach((el) => {
            if (el.dataset.keepScroll) scrolls[el.dataset.keepScroll] = [el.scrollLeft, el.scrollTop];
        });
    });

    function restoreScroll() {
        if (!scrolls) return;
        const view = document.getElementById('task-view');
        if (!view) return;
        const kept = [view, ...view.querySelectorAll('[data-keep-scroll]')];
        kept.forEach((el) => {
            const saved = scrolls[el.dataset.keepScroll];
            if (saved) {
                el.scrollLeft = saved[0];
                el.scrollTop = saved[1];
            }
        });
    }

    function restoreFocus() {
        // The POST settles too, while the old trigger is still there; wait for the refresh.
        if (!refocus || refocus.trigger.isConnected) return;
        const row = document.getElementById(refocus.rowId);
        const twin = row && row.querySelector('[data-quick="' + refocus.kind + '"]');
        if (twin && (!document.activeElement || document.activeElement === document.body)) {
            twin.focus({ preventScroll: true });
        }
        refocus = null;
    }

    // Alpine hides collapsed groups after the swap, so restore again once it has settled.
    document.body.addEventListener('htmx:afterSwap', restoreScroll);
    document.body.addEventListener('htmx:afterSettle', () => {
        restoreScroll();
        scrolls = null;
        restoreFocus();
    });
})();
