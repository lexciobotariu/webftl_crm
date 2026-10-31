// The one place that knows htmx's own event names and the shape of their details.
//
// htmx 2 and htmx 4 name their events differently (htmx:afterRequest vs
// htmx:after:request), fire some of them on different elements, and carry different
// details (event.detail.xhr vs event.detail.ctx). Everything else in the app listens to
// the events below instead, so moving from one htmx version to the other changes this
// file alone. Loaded right after htmx, before any other script.
//
// Events, each dispatched (bubbling) on the element named, with a plain detail:
//
//   request:config  on the element that sends the request, before it goes out.
//                   { source, headers, path, setPath(path) }  headers can be changed.
//   request:start   on the sender, when the request goes out.  { source, target, path }
//   request:end     on the sender, when the answer is in (or the request failed).
//                   { source, target, ok, status, text, path, finalUrl, header(name) }
//   response:error  on the sender, for an answer of 400 or more.  { source, status, text }
//   request:fail    on the sender, when nothing came back or the target is missing.
//                   { source, kind: 'network' | 'target' }
//   swap:before     on the element about to receive the answer.
//                   { source, target, text, path, finalUrl, cancel() }
//   swap:after      on each element the answer went into, right after the swap.
//                   { source, target, path }
//   swap:done       on each element the answer went into, once it has settled.
//                   { source, target, path }
//
// Templates do not write hx-on handlers. Common follow-ups are declared instead:
//
//   data-after-success="reset hide open-drawer"
//       after a successful answer (2xx): reset the form, add the class "hidden",
//       open the drawer (#slide-over).
//   data-after-success-remove="<selector>"
//       after a successful answer, remove the matching elements.
//   data-success-trigger="<eventName>"
//       success also needs the answer to fire that event (HX-Trigger), for views that
//       answer 200 with the form's errors.
//   data-after-request="clear close-drawer"
//       after any answer: empty the field (a file input), close the drawer.
//
// Alpine listens with @request:start / @request:end (detail.ok, detail.text).
(() => {
    if (!window.htmx) return;

    const fire = (element, name, detail) => {
        if (!element || !element.dispatchEvent) return;
        element.dispatchEvent(new CustomEvent(name, { bubbles: true, detail }));
    };

    // --- htmx 2 ---------------------------------------------------------------------
    const sourceOf = (detail) => (detail.requestConfig && detail.requestConfig.elt) || null;
    const pathOf = (detail) => (detail.pathInfo && detail.pathInfo.finalRequestPath)
        || (detail.requestConfig && detail.requestConfig.path) || '';
    const finalUrlOf = (detail) => (detail.xhr && detail.xhr.responseURL) || '';

    document.addEventListener('htmx:configRequest', (event) => {
        const detail = event.detail;
        fire(event.target, 'request:config', {
            source: detail.elt || event.target,
            headers: detail.headers,
            path: detail.path,
            setPath: (path) => { detail.path = path; },
        });
    });

    document.addEventListener('htmx:beforeSend', (event) => {
        const detail = event.detail;
        fire(event.target, 'request:start', {
            source: event.target,
            target: detail.target || null,
            path: pathOf(detail),
        });
    });

    document.addEventListener('htmx:afterRequest', (event) => {
        const detail = event.detail;
        const xhr = detail.xhr;
        fire(event.target, 'request:end', {
            source: event.target,
            target: detail.target || null,
            ok: detail.successful === true,
            status: xhr ? xhr.status : 0,
            text: xhr ? xhr.responseText : '',
            path: pathOf(detail),
            finalUrl: finalUrlOf(detail),
            header: (name) => (xhr ? xhr.getResponseHeader(name) : null),
        });
    });

    document.addEventListener('htmx:responseError', (event) => {
        const xhr = event.detail.xhr;
        fire(event.target, 'response:error', {
            source: event.target,
            status: xhr ? xhr.status : 0,
            text: xhr ? xhr.responseText : '',
        });
    });

    document.addEventListener('htmx:sendError', (event) => {
        fire(event.target, 'request:fail', { source: event.target, kind: 'network' });
    });
    document.addEventListener('htmx:targetError', (event) => {
        fire(event.target, 'request:fail', { source: event.target, kind: 'target' });
    });

    document.addEventListener('htmx:beforeSwap', (event) => {
        const detail = event.detail;
        fire(event.target, 'swap:before', {
            source: sourceOf(detail),
            target: detail.target,
            text: detail.serverResponse || '',
            path: pathOf(detail),
            finalUrl: finalUrlOf(detail),
            cancel: () => { detail.shouldSwap = false; },
        });
    });

    document.addEventListener('htmx:afterSwap', (event) => {
        fire(event.target, 'swap:after', {
            source: sourceOf(event.detail),
            target: event.target,
            path: pathOf(event.detail),
        });
    });

    document.addEventListener('htmx:afterSettle', (event) => {
        fire(event.target, 'swap:done', {
            source: sourceOf(event.detail),
            target: event.target,
            path: pathOf(event.detail),
        });
    });

    // --- Declared follow-ups --------------------------------------------------------
    const words = (element, name) => (element.getAttribute(name) || '').split(/\s+/).filter(Boolean);

    function succeeded(element, detail) {
        if (!detail.ok) return false;
        const needed = element.getAttribute('data-success-trigger');
        return !needed || (detail.header('HX-Trigger') || '').includes(needed);
    }

    document.addEventListener('request:end', (event) => {
        const element = event.target;
        if (!element.getAttribute) return;
        const detail = event.detail;
        if (succeeded(element, detail)) {
            const actions = words(element, 'data-after-success');
            if (actions.includes('reset') && element.reset) element.reset();
            if (actions.includes('hide')) element.classList.add('hidden');
            if (actions.includes('open-drawer') && window.openSlideOver) window.openSlideOver();
            const selector = element.getAttribute('data-after-success-remove');
            if (selector) document.querySelectorAll(selector).forEach((el) => el.remove());
        }
        const always = words(element, 'data-after-request');
        if (always.includes('clear') && 'value' in element) element.value = '';
        if (always.includes('close-drawer') && window.closeSlideOver) window.closeSlideOver();
    });
})();
