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
        setActive(null);
        palette().hidden = false;
        field().focus();
    };

    function closePalette() {
        palette().hidden = true;
        const back = paletteReturn && paletteReturn.isConnected ? paletteReturn : null;
        paletteReturn = null;
        if (back) back.focus({ preventScroll: true });
    }

    function choose(option, newTab) {
        if (!option) return;
        if (option.dataset.detailUrl && !newTab) {
            closePalette();
            htmx.ajax('GET', option.dataset.detailUrl, { target: '#slide-over', swap: 'innerHTML' });
        } else if (newTab) {
            window.open(option.href, '_blank');
        } else {
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
        // Each answer starts on its first result.
        document.addEventListener('htmx:afterSwap', (event) => {
            if (event.detail.target && event.detail.target.id === 'palette-results') setActive(paletteOptions()[0] || null);
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
                choose(options[at], event.ctrlKey || event.metaKey);
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

    document.addEventListener('keydown', function (event) {
        if (event.key.toLowerCase() === 'k' && (event.metaKey || event.ctrlKey) && !event.altKey
            && !event.shiftKey && !event.isComposing) {
            event.preventDefault();
            if (isPaletteOpen()) closePalette();
            else window.openPalette();
        }
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
