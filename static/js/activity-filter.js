// The All / Comments / Work log tabs in templates/tasks/partials/activity_panel.html.
// The filter is only a state on the panel: custom.css hides what it does not match, so
// there is nothing to fetch. Every opening of a task starts on All, so a notification
// that leads to a comment is never behind a tab that hides it.
(function () {
    const ORDER = ['all', 'comments', 'work'];

    document.addEventListener('alpine:init', function () {
        Alpine.data('activityFilter', function () {
            return {
                filter: 'all',

                show(filter, focusTab) {
                    this.filter = filter;
                    if (focusTab) {
                        this.$nextTick(() => this.$refs.tabs.querySelector('[role="tab"][aria-selected="true"]').focus());
                    }
                },

                // Arrow keys move through the tabs, wrapping around (roving tabindex).
                move(step) {
                    const at = ORDER.indexOf(this.filter);
                    this.show(ORDER[(at + step + ORDER.length) % ORDER.length], true);
                },
            };
        });
    });
})();
