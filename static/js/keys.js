// One Escape handler for the whole app. Each layer says whether it handled the
// key; the first that did stops the walk, so one press closes one thing.
// Order, topmost first: palette, help, quick menu, dropdown, drawer, selection.
// A field that handles Escape itself (the title and description editors) calls
// preventDefault first, and this leaves the key alone.
(function () {
    const ORDER = ['palette', 'help', 'menu', 'dropdown', 'drawer', 'selection'];
    const layers = {};

    // A layer is a function(event) that returns true when it closed something.
    window.registerEscLayer = function (name, handler) {
        layers[name] = handler;
    };

    // A dropdown is an Alpine component with `open` and a panel that closes on a click
    // outside it. Collapsible sections also use `open` (the permission preset drawer);
    // they are not something Escape closes.
    const POPOVER = '[\\@click\\.away], [x-on\\:click\\.away], [\\@click\\.outside], [x-on\\:click\\.outside]';

    layers.dropdown = function () {
        if (!window.Alpine) return false;
        for (const el of document.querySelectorAll('[x-data]')) {
            let data;
            try { data = Alpine.$data(el); } catch (error) { continue; }
            if (data && data.open === true && el.querySelector(POPOVER)) {
                data.open = false;
                return true;
            }
        }
        return false;
    };

    layers.drawer = function () {
        const panel = document.getElementById('slide-over');
        if (!panel || panel.classList.contains('hidden')) return false;
        window.closeSlideOver();
        return true;
    };

    // --- Command palette ----------------------------------------------------------
    // Ctrl/Cmd+K or the sidebar button. Search and jump, no actions. The input is a
    // combobox whose options are real links; focus stays in the input and the arrow
    // keys move aria-activedescendant. A task opens in the drawer on the current page,
    // everything else navigates.
    const palette = () => document.getElementById('palette');
    const field = () => document.getElementById('palette-input');
    const isPaletteOpen = () => !!palette() && !palette().hidden;
    const paletteOptions = () => Array.from(palette().querySelectorAll('[role="option"]'));
    let paletteReturn = null;
    let paletteHint = null;
    // The query the listed results answer, and an Enter pressed before they arrived.
    let shownQuery = '';
    let enterPending = false;
    const typedQuery = () => field().value.trim();
    const queryOf = (path) => (new URL(path, window.location.origin).searchParams.get('q') || '').trim();

    function setActive(option) {
        paletteOptions().forEach((el) => el.setAttribute('aria-selected', el === option ? 'true' : 'false'));
        field().setAttribute('aria-activedescendant', option ? option.id : '');
        if (option) option.scrollIntoView({ block: 'nearest' });
    }

    window.openPalette = function () {
        if (!palette() || isPaletteOpen()) return;
        paletteReturn = document.activeElement;
        field().value = '';
        document.getElementById('palette-results').innerHTML = paletteHint;
        shownQuery = '';
        enterPending = false;
        setActive(null);
        palette().hidden = false;
        field().focus();
    };

    function closePalette() {
        palette().hidden = true;
        enterPending = false;
        // A search still on its way must not fill a palette that is closed (or reopened).
        htmx.trigger(field(), 'htmx:abort');
        const back = paletteReturn && paletteReturn.isConnected ? paletteReturn : null;
        paletteReturn = null;
        if (back) back.focus({ preventScroll: true });
    }

    // The task's full page is already showing: the drawer would repeat its element ids
    // (#task-title-<pk> and friends), and an edit in the drawer would land on the page.
    function onItsOwnPage(option) {
        const title = document.getElementById('task-title-' + option.id.replace('palette-task-', ''));
        return !!title && !document.getElementById('slide-over').contains(title);
    }

    function choose(option, newTab) {
        if (!option) return;
        if (newTab) {
            window.open(option.href, '_blank');
        } else if (option.dataset.detailUrl && !onItsOwnPage(option)) {
            closePalette();
            htmx.ajax('GET', option.dataset.detailUrl, { target: '#slide-over', swap: 'innerHTML' });
        } else {
            closePalette();
            window.location.assign(option.href);
        }
    }

    layers.palette = function () {
        if (!isPaletteOpen()) return false;
        closePalette();
        return true;
    };

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-palette-hint]').forEach((el) => {
            if (/Mac|iPhone|iPad/.test(navigator.platform)) el.textContent = '\u2318K';
        });
        if (!palette()) return;
        paletteHint = document.getElementById('palette-results').innerHTML;
        // Only the answer to what is typed now may be shown. An answer to an earlier
        // query (slow network, palette closed and reopened) is dropped, and a redirect
        // means the session ended: go and log in rather than list the login page here.
        document.addEventListener('swap:before', (event) => {
            if (!event.detail.target || event.detail.target.id !== 'palette-results') return;
            const asked = event.detail.path;
            const answered = new URL(event.detail.finalUrl || asked, window.location.origin);
            if (answered.pathname !== new URL(asked, window.location.origin).pathname) {
                event.detail.cancel();
                window.location.reload();
            } else if (!isPaletteOpen() || queryOf(asked) !== typedQuery()) {
                event.detail.cancel();
            }
        });
        // Each answer starts on its first result; an Enter that was waiting for it goes there.
        document.addEventListener('swap:after', (event) => {
            if (!event.detail.target || event.detail.target.id !== 'palette-results') return;
            shownQuery = queryOf(event.detail.path);
            const first = paletteOptions()[0] || null;
            setActive(first);
            if (enterPending) {
                enterPending = false;
                choose(first, false);
            }
        });
        // What is listed no longer answers what is typed, so nothing is selected until it does.
        field().addEventListener('input', () => {
            enterPending = false;
            if (shownQuery !== typedQuery()) setActive(null);
        });
        field().addEventListener('keydown', (event) => {
            const options = paletteOptions();
            const at = options.findIndex((el) => el.getAttribute('aria-selected') === 'true');
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();
                if (!options.length) return;
                const step = event.key === 'ArrowDown' ? 1 : -1;
                setActive(options[(at + step + options.length) % options.length]);
            } else if (event.key === 'Enter' && !event.isComposing) {
                event.preventDefault();
                // Enter typed ahead of the results waits for them instead of opening
                // whatever the previous query had listed.
                if (shownQuery === typedQuery()) choose(options[at], event.ctrlKey || event.metaKey);
                else enterPending = true;
            } else if (event.key === 'Tab') {
                // The input is the only control, so focus stays in the dialog.
                event.preventDefault();
            }
        });
        palette().addEventListener('click', (event) => {
            if (event.target === palette()) {
                closePalette();
                return;
            }
            const option = event.target.closest('[role="option"]');
            // A plain click on a task opens the drawer; a modified click keeps the link's own behaviour.
            if (option && option.dataset.detailUrl && !(event.ctrlKey || event.metaKey || event.shiftKey || event.button)) {
                event.preventDefault();
                choose(option, false);
            }
        });
        palette().addEventListener('mousemove', (event) => {
            const option = event.target.closest('[role="option"]');
            if (option && option.getAttribute('aria-selected') !== 'true') setActive(option);
        });
        palette().addEventListener('focusout', () => {
            setTimeout(() => {
                if (isPaletteOpen() && !palette().contains(document.activeElement)) field().focus();
            }, 0);
        });
    });

    // Cmd+K on a Mac, Ctrl+K elsewhere. On a Mac Ctrl+K is "delete to the end of the
    // line" in a text field and stays that. Autofill sends key events without a key, and
    // pages without a palette (login) leave the shortcut to the browser.
    const isMac = /Mac|iPhone|iPad/.test(navigator.platform);
    document.addEventListener('keydown', function (event) {
        if (!event.key || !palette() || event.key.toLowerCase() !== 'k') return;
        if (!(isMac ? event.metaKey : event.ctrlKey) || event.altKey || event.shiftKey || event.isComposing) return;
        event.preventDefault();
        if (isPaletteOpen()) closePalette();
        else window.openPalette();
    });
    // Back to a page kept whole by the browser: it should not come back with the palette open.
    window.addEventListener('pageshow', function (event) {
        if (event.persisted && isPaletteOpen()) closePalette();
    });

    // --- Keyboard shortcuts list ---------------------------------------------------
    // "?" outside a text field, the sidebar's "Shortcuts" button or the Inbox "?" open
    // #shortcuts (components/shortcuts_dialog.html). The sections for the page you are
    // on move to the top and say "This page".
    const shortcuts = () => document.getElementById('shortcuts');
    let shortcutsReturn = null;
    window.isShortcutsOpen = () => !!shortcuts() && !shortcuts().hidden;

    function scopesHere() {
        const here = [];
        const drawer = document.getElementById('slide-over');
        if (drawer && !drawer.classList.contains('hidden')) here.push('writing');
        if (document.getElementById('inbox')) here.push('inbox');
        if (document.getElementById('task-view')) here.push('tasks');
        if (document.getElementById('doc-lines') && !here.includes('writing')) here.push('writing');
        return here;
    }

    window.showShortcuts = function () {
        const dialog = shortcuts();
        if (!dialog || window.isShortcutsOpen()) return;
        const here = scopesHere();
        const container = dialog.querySelector('[data-shortcuts-sections]');
        const sections = Array.from(container.querySelectorAll('[data-shortcuts-scope]'));
        // The page's own sections first, in the order above, then the rest as written.
        const rank = (el) => {
            const at = here.indexOf(el.dataset.shortcutsScope);
            return at === -1 ? here.length + sections.indexOf(el) : at;
        };
        sections.slice().sort((a, b) => rank(a) - rank(b)).forEach((el) => container.appendChild(el));
        sections.forEach((el) => {
            const tag = el.querySelector('[data-shortcuts-here]');
            if (tag) tag.hidden = !here.includes(el.dataset.shortcutsScope);
        });
        container.scrollTop = 0;
        shortcutsReturn = document.activeElement;
        dialog.hidden = false;
        // The list takes focus so the arrow keys scroll it.
        container.focus();
    };

    function hideShortcuts() {
        shortcuts().hidden = true;
        const back = shortcutsReturn && shortcutsReturn.isConnected ? shortcutsReturn : null;
        shortcutsReturn = null;
        if (back && back !== document.body) back.focus({ preventScroll: true });
    }

    layers.help = function () {
        if (!window.isShortcutsOpen()) return false;
        hideShortcuts();
        return true;
    };

    const typingIn = (el) => !!el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
    document.addEventListener('keydown', function (event) {
        if (event.key !== '?' || event.defaultPrevented || event.isComposing || event.repeat) return;
        if (event.ctrlKey || event.metaKey || event.altKey || typingIn(event.target)) return;
        if (!shortcuts() || isPaletteOpen()) return;
        event.preventDefault();
        if (window.isShortcutsOpen()) hideShortcuts();
        else window.showShortcuts();
    });

    document.addEventListener('DOMContentLoaded', function () {
        const dialog = shortcuts();
        if (!dialog) return;
        dialog.addEventListener('click', (event) => {
            if (event.target === dialog || event.target.closest('[data-shortcuts-close]')) hideShortcuts();
        });
        // Tab moves between the list and Close and stays inside the dialog.
        dialog.addEventListener('keydown', (event) => {
            if (event.key !== 'Tab') return;
            event.preventDefault();
            const close = dialog.querySelector('[data-shortcuts-close]');
            (document.activeElement === close ? dialog.querySelector('[data-shortcuts-sections]') : close).focus();
        });
    });

    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape' || event.defaultPrevented || event.isComposing) return;
        for (const name of ORDER) {
            const handler = layers[name];
            if (handler && handler(event)) {
                event.preventDefault();
                return;
            }
        }
    });
})();
