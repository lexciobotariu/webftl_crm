// Live updates on the task pages (list, board, My Tasks, task page, and the drawer
// opened over them). The server sends one "task" event when anyone else changes a
// task: a colleague, Claude (MCP), the GitHub webhook (apps/live). The page then
// re-fetches what it shows through the usual views, after the person finishes
// whatever they are editing, and briefly marks the rows that changed.
(() => {
    const config = document.getElementById('live-tasks');
    if (!config || !window.EventSource || window.liveTasks) return;

    // This tab's id rides on every request it makes, so the server leaves its own
    // changes out of this tab's stream (the response already updated it).
    const tab = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Math.random()).slice(2);
    window.liveTasks = { tab };
    document.body.addEventListener('htmx:configRequest', (event) => {
        event.detail.headers['X-Tab-Id'] = tab;
    });

    const pending = { view: false, drawer: false, page: false, tasks: new Set() };
    let timer = null;

    // --- Is the person in the middle of something? -------------------------------
    const isField = (el) => !!el && (el.matches('input, textarea, select') || el.isContentEditable);

    function dropdownOpen(root) {
        if (!root || !window.Alpine) return false;
        return [...root.querySelectorAll('[x-data]')].some((el) => {
            try { return Alpine.$data(el).open === true; } catch (e) { return false; }
        });
    }

    // Something typed and not yet sent (a comment, a description) must survive.
    function hasDraft(root) {
        return [...root.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]), textarea')]
            .some((el) => el.value !== el.defaultValue);
    }

    function busyIn(root) {
        if (!root) return false;
        return root.contains(document.activeElement) && isField(document.activeElement)
            || dropdownOpen(root) || hasDraft(root)
            || !!root.querySelector('[aria-expanded="true"]');
    }

    function viewBusy() {
        const menu = document.getElementById('task-quick-menu');
        if (menu && !menu.hidden) return true;
        // A card being dragged on the board.
        if (document.querySelector('.sortable-chosen, .sortable-drag')) return true;
        return busyIn(document.getElementById('task-view'));
    }

    const drawer = () => document.getElementById('slide-over');
    const drawerTask = () => {
        const panel = drawer();
        if (!panel || panel.classList.contains('hidden')) return null;
        return panel.querySelector('[data-live-task]');
    };
    const fullPage = () => document.querySelector('[data-live-page]');

    // --- Refreshing --------------------------------------------------------------
    function flash(ids) {
        ids.forEach((id) => {
            document.querySelectorAll('#task-view #task-' + id).forEach((row) => {
                row.classList.remove('live-flash');
                void row.offsetWidth; // restart the animation when it changes twice
                row.classList.add('live-flash');
                row.addEventListener('animationend', () => row.classList.remove('live-flash'), { once: true });
            });
        });
    }

    function refreshView() {
        const changed = [...pending.tasks];
        pending.view = false;
        pending.tasks.clear();
        const done = window.refreshTaskView ? window.refreshTaskView() : null;
        if (done && done.then) done.then(() => flash(changed));
    }

    // The drawer is re-fetched whole; its scroll position is kept.
    function refreshDrawer(el) {
        pending.drawer = false;
        const panel = drawer();
        const scrolled = [...panel.querySelectorAll('.overflow-y-auto')].map((box) => box.scrollTop);
        htmx.ajax('GET', el.dataset.liveUrl, { target: '#slide-over', swap: 'innerHTML' }).then(() => {
            panel.querySelectorAll('.overflow-y-auto').forEach((box, i) => {
                if (scrolled[i]) box.scrollTop = scrolled[i];
            });
            if (window.lucide) lucide.createIcons();
        });
    }

    function refreshPage(el) {
        pending.page = false;
        const selector = '#' + el.id;
        const scrolled = [...el.querySelectorAll('.overflow-y-auto')].map((box) => box.scrollTop);
        htmx.ajax('GET', window.location.href, { target: selector, select: selector, swap: 'outerHTML' }).then(() => {
            const fresh = document.querySelector(selector);
            if (fresh) fresh.querySelectorAll('.overflow-y-auto').forEach((box, i) => {
                if (scrolled[i]) box.scrollTop = scrolled[i];
            });
            if (window.lucide) lucide.createIcons();
        });
    }

    // Runs what is due, and comes back every second for what has to wait.
    function run() {
        timer = null;
        if (document.hidden) return; // caught up when the tab is shown again
        if (pending.view && document.getElementById('task-view')) {
            if (!viewBusy()) refreshView();
        } else {
            pending.view = false;
        }
        const open = drawerTask();
        if (pending.drawer && open) {
            if (!busyIn(drawer())) refreshDrawer(open);
        } else {
            pending.drawer = false;
        }
        const page = fullPage();
        if (pending.page && page) {
            if (!busyIn(page)) refreshPage(page);
        } else {
            pending.page = false;
        }
        if (pending.view || pending.drawer || pending.page) timer = setTimeout(run, 1000);
    }

    // Several changes in a row (Claude often makes a few) become one refresh.
    function schedule(delay) {
        if (timer) clearTimeout(timer);
        timer = setTimeout(run, delay);
    }

    function changed(taskId) {
        pending.view = true;
        if (taskId) pending.tasks.add(taskId);
        const open = drawerTask();
        if (open && (!taskId || String(taskId) === open.dataset.liveTask)) pending.drawer = true;
        const page = fullPage();
        if (page && (!taskId || String(taskId) === page.dataset.livePage)) pending.page = true;
        schedule(300);
    }

    document.addEventListener('visibilitychange', () => {
        if (!document.hidden && (pending.view || pending.drawer || pending.page)) schedule(0);
    });

    // --- The connection ----------------------------------------------------------
    const url = new URL(config.dataset.url, window.location.origin);
    url.searchParams.set('tab', tab);
    const source = new EventSource(url);
    let connected = false;
    source.addEventListener('ready', () => {
        // Back after a drop (deploy, network, the hourly reconnect): changes made in
        // between were not heard, so reload once.
        if (connected) changed(null);
        connected = true;
    });
    source.addEventListener('resync', () => changed(null));
    source.addEventListener('task', (event) => {
        let data = {};
        try { data = JSON.parse(event.data); } catch (e) { return; }
        changed(data.task);
    });
    window.addEventListener('pagehide', () => source.close());
})();
