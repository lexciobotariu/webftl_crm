// The @ menu in the comment box (templates/tasks/partials/markdown_editor.html with
// mentions_id). Typing "@" and part of a name lists the people who can see the task;
// the arrows move, Enter or Tab picks, Escape closes the menu only. Focus stays in the
// textarea, which points at the active option with aria-activedescendant, like the
// command palette. A pick writes "@Name " into the text and adds a hidden "mentions"
// input; the server keeps an id only while its "@Name" is still in the text.
(function () {
    const LIMIT = 6;
    let open = null; // { textarea, menu, start, matches, active }

    function peopleFor(textarea) {
        const source = document.getElementById(textarea.dataset.mentions);
        if (!source) return [];
        if (!source._people) {
            try { source._people = JSON.parse(source.textContent); } catch (error) { source._people = []; }
        }
        return source._people;
    }

    // The "@query" that ends at the caret, if any: the @ starts the text or follows a space.
    function trigger(textarea) {
        const before = textarea.value.slice(0, textarea.selectionStart);
        const match = /(^|\s)@([^@\n]{0,30})$/.exec(before);
        if (!match) return null;
        return { start: before.length - match[2].length - 1, query: match[2].toLowerCase() };
    }

    function matchesFor(textarea, query) {
        return peopleFor(textarea).filter((person) => {
            const name = person.name.toLowerCase();
            return name.startsWith(query) || name.split(/\s+/).some((word) => word.startsWith(query));
        }).slice(0, LIMIT);
    }

    function close() {
        if (!open) return;
        open.menu.hidden = true;
        open.menu.replaceChildren();
        open.textarea.removeAttribute('aria-activedescendant');
        open = null;
    }

    function setActive(index) {
        open.active = index;
        open.menu.querySelectorAll('[role="option"]').forEach((option, i) => {
            option.setAttribute('aria-selected', i === index ? 'true' : 'false');
            if (i === index) {
                open.textarea.setAttribute('aria-activedescendant', option.id);
                option.scrollIntoView({ block: 'nearest' });
            }
        });
    }

    function render(textarea, start, matches) {
        const menu = document.getElementById(textarea.getAttribute('aria-controls'));
        if (!menu) return;
        if (!matches.length) { close(); return; }
        open = { textarea, menu, start, matches, active: 0 };
        menu.replaceChildren(...matches.map((person) => {
            const option = document.createElement('li');
            option.id = `${menu.id}-${person.id}`;
            option.setAttribute('role', 'option');
            option.dataset.index = String(matches.indexOf(person));
            option.className = 'px-3 py-1.5 text-sm text-zinc-300 cursor-pointer aria-selected:bg-hover-strong aria-selected:text-zinc-100';
            option.textContent = person.name;
            return option;
        }));
        menu.hidden = false;
        setActive(0);
    }

    function pick(index) {
        const { textarea, start, matches } = open;
        const person = matches[index];
        const caret = textarea.selectionStart;
        const insert = `@${person.name} `;
        textarea.value = textarea.value.slice(0, start) + insert + textarea.value.slice(caret);
        const position = start + insert.length;
        textarea.setSelectionRange(position, position);
        const form = textarea.closest('form');
        if (form && !form.querySelector(`input[data-mention][value="${person.id}"]`)) {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'mentions';
            input.value = String(person.id);
            input.dataset.mention = '';
            form.appendChild(input);
        }
        close();
        textarea.focus();
    }

    document.addEventListener('input', (event) => {
        const textarea = event.target;
        if (!(textarea instanceof HTMLTextAreaElement) || !textarea.dataset.mentions) return;
        const found = trigger(textarea);
        if (!found) { close(); return; }
        render(textarea, found.start, matchesFor(textarea, found.query));
    });

    document.addEventListener('keydown', (event) => {
        if (!open || event.target !== open.textarea || event.isComposing) return;
        const count = open.matches.length;
        if (event.key === 'ArrowDown') {
            event.preventDefault();
            setActive((open.active + 1) % count);
        } else if (event.key === 'ArrowUp') {
            event.preventDefault();
            setActive((open.active - 1 + count) % count);
        } else if ((event.key === 'Enter' || event.key === 'Tab') && !event.ctrlKey && !event.metaKey && !event.shiftKey) {
            event.preventDefault();
            pick(open.active);
        } else if (event.key === 'Escape') {
            // Marked handled: the drawer and the editor leave this Escape alone.
            event.preventDefault();
            close();
        }
    }, true);

    // A pick by mouse; mousedown so the textarea keeps focus.
    document.addEventListener('mousedown', (event) => {
        if (!open) return;
        const option = event.target.closest('[role="option"]');
        if (option && open.menu.contains(option)) {
            event.preventDefault();
            pick(Number(option.dataset.index));
        } else if (event.target !== open.textarea) {
            close();
        }
    });

    document.addEventListener('focusout', (event) => {
        if (open && event.target === open.textarea) close();
    });

    // A posted comment resets its form; the picks go with the text.
    document.addEventListener('reset', (event) => {
        event.target.querySelectorAll('input[data-mention]').forEach((input) => input.remove());
        close();
    }, true);
})();
