// One Escape handler for the whole app. Each layer says whether it handled the
// key; the first that did stops the walk, so one press closes one thing.
// Order, topmost first: help, palette, quick menu, dropdown, drawer, selection.
// A field that handles Escape itself (the title and description editors) calls
// preventDefault first, and this leaves the key alone.
(function () {
    const ORDER = ['help', 'palette', 'menu', 'dropdown', 'drawer', 'selection'];
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
