// The one place that knows htmx's own event names and the shape of their details.
//
// htmx 2 and htmx 4 name their events differently (htmx:afterRequest vs
// htmx:after:request), fire some of them on different elements, and carry different
// details (event.detail.xhr vs event.detail.ctx). Everything else in the app listens to
// the events below instead, so a change of htmx version changes this file alone. This is
// the htmx 4 version (0.41.0); 0.40.3 has the htmx 2 one. Loaded right after htmx.
//
// Events, each dispatched (bubbling) on the element named, with a plain detail:
//
//   request:config  on the element that sends the request, before it goes out.
//                   { source, headers, path, setPath(path) }  headers can be changed.
//   request:start   on the sender, when the request goes out.  { source, target, path }
//   request:end     on the sender, once the answer is swapped in (or the request failed
//                   or was aborted: status 0).
//                   { source, target, ok, status, text, path, finalUrl, header(name) }
//   response:error  on the sender, for an answer of 400 or more.  { source, status, text }
//   request:fail    on the sender, when nothing came back or the swap failed (not for
//                   a request that was aborted).  { source, kind: 'network' | 'swap' }
//   swap:before     on the element about to receive the answer.
//                   { source, target, text, path, finalUrl, cancel() }
//   swap:after      on the element the main answer went into, right after the swap.
//                   { source, target, path }
//   swap:done       on each element the answer went into (out-of-band ones too),
//                   once it has settled.
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
//
// HX-Trigger events still fire before the swap, from the sender, as in htmx 2; the
// HX-Trigger-After-Swap / -After-Settle headers htmx 4 dropped fire after it.
(() => {
    if (!window.htmx) return;

    const fire = (element, name, detail) => {
        if (!element || !element.dispatchEvent) return;
        element.dispatchEvent(new CustomEvent(name, { bubbles: true, detail }));
    };

    // --- htmx 4 ---------------------------------------------------------------------
    // Every request event carries detail.ctx: ctx.sourceElement, ctx.target, ctx.request
    // (action, headers), ctx.response (status, headers, raw), ctx.text. Swap events also
    // carry the swap tasks: one "main" task, plus one per out-of-band element.
    const ctxOf = (event) => (event.detail && event.detail.ctx) || null;
    const sourceOf = (ctx) => (ctx && (ctx.appSource || ctx.sourceElement)) || null;
    const pathOf = (ctx) => (ctx && ctx.request && ctx.request.action) || '';
    const statusOf = (ctx) => (ctx && ctx.response ? ctx.response.status : 0);
    const finalUrlOf = (ctx) => (ctx && ctx.response && ctx.response.raw && ctx.response.raw.url) || '';
    const headerOf = (ctx, name) => (ctx && ctx.response && ctx.response.headers ? ctx.response.headers.get(name) : null);

    // HX-Trigger as htmx 2 fired it: from the element that sent the request, before the
    // swap. htmx 4 fires it after the swap, from wherever the swap left the source, and
    // listeners here (closeSlideOver, taskChanged on a quick-edit row) expect the former.
    function fireTriggerHeader(value, element) {
        if (!value) return;
        const on = element && element.isConnected ? element : document.body;
        if (value.trim()[0] === '{') {
            let events;
            try { events = JSON.parse(value); } catch (e) { return; }
            Object.keys(events).forEach((name) => {
                const detail = events[name];
                const target = detail && detail.target ? document.querySelector(detail.target) : on;
                htmx.trigger(target || on, name, detail !== null && typeof detail === 'object' ? detail : { value: detail });
            });
        } else {
            value.split(',').forEach((name) => { if (name.trim()) htmx.trigger(on, name.trim(), {}); });
        }
    }

    document.addEventListener('htmx:config:request', (event) => {
        const ctx = ctxOf(event);
        if (!ctx) return;
        ctx.appSource = ctx.sourceElement;
        fire(ctx.sourceElement, 'request:config', {
            source: ctx.sourceElement,
            headers: ctx.request.headers,
            path: ctx.request.action,
            setPath: (path) => { ctx.request.action = path; },
        });
    });

    document.addEventListener('htmx:before:request', (event) => {
        const ctx = ctxOf(event);
        if (!ctx) return;
        const source = sourceOf(ctx);
        // Where request:end goes if the answer replaces the sender (htmx 2 did the same):
        // the nearest element around it that is still on the page.
        ctx.appAncestors = [];
        for (let el = source && source.parentElement; el; el = el.parentElement) ctx.appAncestors.push(el);
        fire(source, 'request:start', { source, target: ctx.target || null, path: pathOf(ctx) });
    });

    document.addEventListener('htmx:after:request', (event) => {
        const ctx = ctxOf(event);
        if (!ctx || !ctx.hx || !ctx.hx.trigger) return;
        const value = ctx.hx.trigger;
        ctx.hx.trigger = null; // fired here, so htmx does not fire it again after the swap
        fireTriggerHeader(value, sourceOf(ctx));
    });

    document.addEventListener('htmx:response:error', (event) => {
        const ctx = ctxOf(event);
        if (!ctx) return;
        fire(sourceOf(ctx), 'response:error', { source: sourceOf(ctx), status: statusOf(ctx), text: ctx.text || '' });
    });

    document.addEventListener('htmx:error', (event) => {
        const ctx = ctxOf(event);
        const error = event.detail && event.detail.error;
        // Not a failure: hx-sync="replace" (or htmx:abort) cancelled a request still in flight.
        if (!ctx || (error && error.name === 'AbortError')) return;
        fire(sourceOf(ctx), 'request:fail', { source: sourceOf(ctx), kind: ctx.response ? 'swap' : 'network' });
    });

    document.addEventListener('htmx:finally:request', (event) => {
        const ctx = ctxOf(event);
        if (!ctx) return;
        const source = sourceOf(ctx);
        const status = statusOf(ctx);
        const detail = {
            source,
            target: ctx.target || null,
            ok: status >= 200 && status < 400 && !String(ctx.status).startsWith('error'),
            status,
            text: ctx.text || '',
            path: pathOf(ctx),
            finalUrl: finalUrlOf(ctx),
            header: (name) => headerOf(ctx, name),
        };
        ended(source, detail, ctx.appAncestors || []);
        // htmx 4 dropped these two; one view still sends HX-Trigger-After-Settle.
        fireTriggerHeader(headerOf(ctx, 'HX-Trigger-After-Swap'), source);
        fireTriggerHeader(headerOf(ctx, 'HX-Trigger-After-Settle'), source);
    });

    document.addEventListener('htmx:before:swap', (event) => {
        const ctx = ctxOf(event);
        if (!ctx) return;
        const tasks = event.detail.tasks || [];
        tasks.forEach((task) => { task.appCtx = ctx; });
        const main = tasks.find((task) => task.type === 'main');
        const target = (main && main.target) || ctx.target || null;
        fire(target instanceof Element ? target : sourceOf(ctx), 'swap:before', {
            source: sourceOf(ctx),
            target,
            text: ctx.text || '',
            path: pathOf(ctx),
            finalUrl: finalUrlOf(ctx),
            cancel: () => event.preventDefault(),
        });
    });

    // Fired on each element a task swapped into: swap:after for the main swap only (as
    // htmx 2's afterSwap), swap:done for the main swap and every out-of-band one.
    // After an outerHTML swap htmx 4 names the first new node, which is a text node
    // when the answer starts with a line break; the element is the one after it.
    const swappedElement = (event) => {
        if (event.target instanceof Element) return event.target;
        const fresh = (event.detail.newContent || []).find((node) => node instanceof Element);
        return fresh || (event.target && event.target.parentElement) || null;
    };
    const swapDetail = (event, target) => {
        const task = event.detail.task || {};
        return { source: sourceOf(task.appCtx) || task.sourceElement || null, target, path: pathOf(task.appCtx) };
    };
    document.addEventListener('htmx:before:settle', (event) => {
        const task = event.detail.task;
        const target = swappedElement(event);
        if (task && task.type === 'main') fire(target, 'swap:after', swapDetail(event, target));
    });
    document.addEventListener('htmx:after:settle', (event) => {
        const target = swappedElement(event);
        fire(target, 'swap:done', swapDetail(event, target));
    });

    // --- Declared follow-ups --------------------------------------------------------
    const words = (element, name) => (element.getAttribute(name) || '').split(/\s+/).filter(Boolean);

    function succeeded(element, detail) {
        if (!detail.ok) return false;
        const needed = element.getAttribute('data-success-trigger');
        return !needed || (detail.header('HX-Trigger') || '').includes(needed);
    }

    function followUps(element, detail) {
        if (!element || !element.getAttribute) return;
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
    }

    // request:end on the sender; when the answer replaced it, also on the nearest element
    // that was around it and is still on the page, so listeners there still hear it.
    function ended(source, detail, ancestors) {
        fire(source, 'request:end', detail);
        if (source && !source.isConnected) {
            const around = ancestors.find((el) => el.isConnected);
            if (around) fire(around, 'request:end', detail);
        }
        followUps(source, detail);
    }
})();
