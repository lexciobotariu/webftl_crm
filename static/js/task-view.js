// The Tasks page and My Tasks: the quick-edit menu on rows and cards, the keyboard
// selection and shortcuts, and scroll that survives a refresh of #task-view. One menu
// element (#task-quick-menu) serves every row; a delegated listener opens it from any
// [data-quick] button. People who cannot edit get no menu, only the selection.
(function () {
    if (window.__taskViewLoaded) return;
    window.__taskViewLoaded = true;

    const menu = () => document.getElementById('task-quick-menu');
    const LABELS = { priority: 'Set priority', status: 'Set status', assignee: 'Set assignee' };
    let state = null; // the open menu: { trigger, kind, pk, rowId, token, top, left, viaKey }
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
        const { trigger, kind, rowId, viaKey } = state;
        const m = menu();
        state = null;
        token += 1;
        m.hidden = true;
        m.replaceChildren();
        trigger.setAttribute('aria-expanded', 'false');
        if (!returnFocus) return;
        if (viaKey) {
            // Opened with S / P / A: the row is where the person was.
            const row = document.getElementById(rowId);
            if (row) row.focus({ preventScroll: true });
        } else if (trigger.isConnected) {
            trigger.focus({ preventScroll: true });
        }
        // A refresh replaces the trigger; its twin in the new list takes the focus.
        refocus = { trigger, rowId, kind, viaKey };
        // If no refresh follows, don't let a much later swap pull focus back.
        setTimeout(() => { if (refocus && refocus.rowId === rowId) refocus = null; }, 4000);
    }

    function openMenu(trigger, viaKey) {
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
        state = { trigger, kind, pk: row.id.replace('task-', ''), rowId: row.id, token: mine, top: at.top, left: at.left, viaKey: !!viaKey };
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
                // fetch follows a redirect to the login page and reports 200 for it.
                if (!response.ok || response.redirected) throw new Error('quick menu ' + response.status);
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
        // Clicking a row or card makes it the selection, so the keys carry on from there.
        const clicked = event.target.closest('[data-task-row]');
        if (clicked && !event.target.closest('a')) select(clicked, { focus: false });
        const trigger = event.target.closest('[data-quick]');
        if (trigger) {
            event.preventDefault();
            openMenu(trigger);
            return;
        }
        if (state && !menu().contains(event.target)) closeMenu(false);
    });

    document.addEventListener('DOMContentLoaded', () => {
        if (!menu()) return;
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

    // --- Selection and shortcuts ----------------------------------------------
    // The selected row or card is the one keys act on. It carries .task-selected,
    // tabindex, aria-current and real focus; the id is remembered so a refresh can
    // put the selection back on the new copy of the same row.
    const view = () => document.getElementById('task-view');
    let selectedId = null;
    let selectedPos = { col: null, idx: 0 };

    const isShown = (el) => el.getClientRects().length > 0;
    const board = () => document.getElementById('kanban-board-content');
    const allRows = () => (view() ? Array.from(view().querySelectorAll('[data-task-row]')).filter(isShown) : []);
    const columnOf = (row) => row.closest('#kanban-board-content > [id^="column-"]');
    const columnRows = (col) => allRows().filter((row) => columnOf(row) === col);
    const selectedRow = () => (selectedId ? document.getElementById(selectedId) : null);
    const isIdle = () => !document.activeElement || document.activeElement === document.body;

    function clearSelection() {
        document.querySelectorAll('.task-selected').forEach((el) => {
            el.classList.remove('task-selected');
            el.removeAttribute('aria-current');
            el.removeAttribute('tabindex');
        });
    }

    function select(row, options) {
        const { focus = true, preventScroll = false } = options || {};
        clearSelection();
        row.classList.add('task-selected');
        row.setAttribute('aria-current', 'true');
        row.tabIndex = 0;
        selectedId = row.id;
        const col = board() ? columnOf(row) : null;
        const peers = col ? columnRows(col) : allRows();
        selectedPos = { col: col ? col.id : null, idx: Math.max(0, peers.indexOf(row)) };
        if (focus) row.focus({ preventScroll });
    }

    function deselect() {
        clearSelection();
        selectedId = null;
    }

    // Where the selection goes when its row is gone: same place in the list or column.
    function fallbackRow() {
        const rows = allRows();
        const col = selectedPos.col && document.getElementById(selectedPos.col);
        const peers = col ? columnRows(col) : rows;
        const pool = peers.length ? peers : rows;
        return pool[Math.min(selectedPos.idx, pool.length - 1)] || null;
    }

    function reselect() {
        if (!selectedId) return;
        let row = selectedRow();
        if (!row || !isShown(row)) row = fallbackRow();
        if (!row) {
            selectedId = null;
            return;
        }
        // Only take focus back when nothing else has it: a refresh replaces the row
        // the person was on, but never pulls focus out of the search box or the drawer.
        select(row, { focus: isIdle(), preventScroll: true });
    }

    function step(direction) {
        const rows = allRows();
        if (!rows.length) return;
        const current = selectedRow();
        if (!current || !isShown(current)) {
            select(rows[0]);
            return;
        }
        let target = null;
        if (!board()) {
            const at = rows.indexOf(current);
            if (direction === 'next') target = rows[at + 1];
            else if (direction === 'prev') target = rows[at - 1];
        } else if (direction === 'next' || direction === 'prev') {
            const peers = columnRows(columnOf(current));
            target = peers[peers.indexOf(current) + (direction === 'next' ? 1 : -1)];
        } else {
            const columns = Array.from(board().children).filter((el) => el.id.startsWith('column-'));
            const here = columnOf(current);
            const index = columnRows(here).indexOf(current);
            const stride = direction === 'right' ? 1 : -1;
            for (let at = columns.indexOf(here) + stride; at >= 0 && at < columns.length; at += stride) {
                const peers = columnRows(columns[at]);
                if (peers.length) {
                    target = peers[Math.min(index, peers.length - 1)];
                    break;
                }
            }
        }
        if (target) select(target);
    }

    const isField = (el) => !!el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
    const drawerOpen = () => !document.getElementById('slide-over').classList.contains('hidden');
    const help = () => document.getElementById('task-shortcuts');
    const helpOpen = () => !!help() && !help().hidden;

    function openSelected() {
        const row = selectedRow();
        if (!row) return;
        const url = row.dataset.detailUrl || row.getAttribute('hx-get');
        if (url) htmx.ajax('GET', url, { target: '#slide-over', swap: 'innerHTML' });
    }

    let helpReturn = null;
    function showHelp() {
        helpReturn = document.activeElement;
        help().hidden = false;
        help().querySelector('[role="dialog"]').focus();
    }
    function hideHelp() {
        help().hidden = true;
        const back = helpReturn && helpReturn.isConnected ? helpReturn : selectedRow();
        helpReturn = null;
        if (back) back.focus({ preventScroll: true });
    }

    document.addEventListener('keydown', (event) => {
        if (!event.key || event.defaultPrevented || event.isComposing || event.keyCode === 229) return;
        if (event.ctrlKey || event.metaKey || event.altKey) return;
        // The menu and the drawer own the keyboard while they are open.
        if (state || drawerOpen() || helpOpen()) return;
        const target = event.target;
        if (isField(target)) return;
        const inView = target === document.body || target === document.documentElement
            || (view() && view().contains(target));
        if (!inView) return;

        const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
        const handled = () => event.preventDefault();
        if (key === 'j' || key === 'ArrowDown') { handled(); step('next'); }
        else if (key === 'k' || key === 'ArrowUp') { handled(); step('prev'); }
        else if (board() && (key === 'h' || key === 'ArrowLeft')) { handled(); step('left'); }
        else if (board() && (key === 'l' || key === 'ArrowRight')) { handled(); step('right'); }
        else if (key === 'Enter') {
            // On a focused button Enter is that button's click, not "open the task".
            if (selectedRow() && (target === document.body || target.hasAttribute('data-task-row'))) {
                handled();
                openSelected();
            }
        } else if (key === '/') {
            const search = document.getElementById('task-search');
            if (search) { handled(); search.focus(); search.select(); }
        } else if (key === 'c') {
            const create = document.getElementById('task-new');
            if (create) { handled(); create.click(); }
        } else if (key === '?') {
            if (help()) { handled(); showHelp(); }
        } else if (key === 's' || key === 'p' || key === 'a') {
            const row = selectedRow();
            const kind = { s: 'status', p: 'priority', a: 'assignee' }[key];
            const trigger = row && row.querySelector('[data-quick="' + kind + '"]');
            if (trigger) { handled(); openMenu(trigger, true); }
        }
    });

    // Escape in the search box leaves it. Capture phase, so it runs before the app-wide
    // Escape handler and that one sees the key as already dealt with.
    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape' || event.target.id !== 'task-search') return;
        event.preventDefault();
        event.target.blur();
        const row = selectedRow();
        if (row) row.focus({ preventScroll: true });
    }, true);

    document.addEventListener('DOMContentLoaded', () => {
        if (!help()) return;
        help().addEventListener('click', (event) => {
            if (event.target === help() || event.target.closest('[data-shortcuts-close]')) hideHelp();
        });
        // Close is the only control, so Tab lands on it and stays inside the dialog.
        help().addEventListener('keydown', (event) => {
            if (event.key !== 'Tab') return;
            event.preventDefault();
            help().querySelector('[data-shortcuts-close]').focus();
        });
    });

    window.registerEscLayer('help', () => {
        if (!helpOpen()) return false;
        hideHelp();
        return true;
    });
    window.registerEscLayer('selection', () => {
        if (!selectedId) return false;
        const row = selectedRow();
        deselect();
        if (row && row === document.activeElement) row.blur();
        return true;
    });
    // Back from the drawer lands on the row it was opened from.
    document.addEventListener('slideover:closed', () => {
        const row = selectedRow();
        if (row && isIdle()) row.focus({ preventScroll: true });
    });

    // --- Scroll that survives a refresh -------------------------------------
    // A refresh replaces #task-view; without this every edit would send the list
    // back to the top. Elements opt in with data-keep-scroll="<key>".
    let scrolls = null;

    // A change made in the toolbar (filter, layout, search) is a different view and
    // starts at the top. Everything else that swaps #task-view is the same view again:
    // the refresh after an edit, "Show more", and the board's refresh after a drag.
    function isRefresh(detail) {
        const source = detail.requestConfig && detail.requestConfig.elt;
        return !(source && source.closest && source.closest('#task-toolbar'));
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
        // A keyboard-opened menu returns to the row, which the selection takes back below.
        if (twin && !refocus.viaKey && (!document.activeElement || document.activeElement === document.body)) {
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
        reselect();
    });
})();
