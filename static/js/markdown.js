// The Write / Preview editor in templates/tasks/partials/markdown_editor.html.
// The preview is rendered by the server with the same filter as the saved text, so
// what you see is what gets shown. It handles its own Escape: in Preview the key goes
// back to Write and marks itself handled, so the app-wide layer (keys.js) does not
// also close the drawer.
(function () {
    function csrfToken() {
        const input = document.querySelector('[name="csrfmiddlewaretoken"]');
        if (input) return input.value;
        try {
            return JSON.parse(document.body.getAttribute('hx-headers') || '{}')['X-CSRFToken'];
        } catch (error) {
            return null;
        }
    }

    document.addEventListener('alpine:init', function () {
        Alpine.data('markdownEditor', function (previewUrl) {
            return {
                tab: 'write',
                loading: false,
                request: 0,

                init() {
                    const form = this.$el.closest('form');
                    if (form) form.addEventListener('reset', () => { this.tab = 'write'; });
                },

                show(tab, focusTab) {
                    this.tab = tab;
                    if (tab === 'preview') this.renderPreview();
                    this.$nextTick(() => {
                        if (focusTab) this.$el.querySelector(`[role="tab"][aria-selected="true"]`).focus();
                        else if (tab === 'write') this.$refs.input.focus();
                    });
                },

                async renderPreview() {
                    const id = ++this.request;
                    const body = new FormData();
                    body.append('text', this.$refs.input.value);
                    const token = csrfToken();
                    this.loading = true;
                    let html;
                    try {
                        const response = await fetch(previewUrl, {
                            method: 'POST',
                            body,
                            credentials: 'same-origin',
                            headers: token ? { 'X-CSRFToken': token } : {},
                        });
                        html = response.ok ? await response.text() : '<p class="text-error">Preview is not available.</p>';
                    } catch (error) {
                        html = '<p class="text-error">Preview is not available.</p>';
                    }
                    // A later request (typing, then Preview again) wins.
                    if (id !== this.request) return;
                    this.loading = false;
                    this.$refs.preview.innerHTML = html;
                },

                escape(event) {
                    if (this.tab !== 'preview') return;
                    event.preventDefault();
                    this.show('write');
                },

                submit() {
                    const form = this.$el.closest('form');
                    if (form) form.requestSubmit();
                },
            };
        });
    });
})();
