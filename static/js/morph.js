// hx-swap="morph": instead of throwing the old element away, Alpine's morph plugin
// changes only what differs between it and the new HTML. Focus, scroll positions and
// Alpine state (an open tab, a panel hidden by x-show) survive, and htmx's settle step,
// which puts a swapped element's original style back over x-show, never runs.
// Elements are matched by id, so a row that moved is moved, not rewritten in place.
// Used where a whole view is re-fetched: the task list and board, the open drawer and
// the task page (templates/tasks/view/_view_scripts.html, static/js/live.js).
htmx.defineExtension('morph', {
    isInlineSwap: (swapStyle) => swapStyle === 'morph',
    handleSwap: (swapStyle, target, fragment) => {
        if (swapStyle !== 'morph') return false;
        const fresh = fragment.firstElementChild;
        if (!fresh) return [];
        // Without the plugin (a CDN hiccup) it is a plain outerHTML swap.
        if (!window.Alpine || !Alpine.morph) {
            target.replaceWith(fresh);
            return [fresh];
        }
        Alpine.morph(target, fresh, { key: (el) => el.id });
        return [target];
    },
});
