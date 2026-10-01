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
