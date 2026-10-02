# Tasks roadmap

What was planned for the tasks side of the CRM, what shipped, and the decisions
behind it. Read this before planning new work on tasks, time tracking or the Inbox,
so a new plan continues from what was decided instead of re-deciding it.

Three documents cover the same work from different sides:

| Document | What it records |
|---|---|
| `CHANGELOG.md` | What changed in each version, in the words a user would recognise. The in-app changelog page reads it. |
| `docs/ui-patterns.md` | How the UI is built: components, events, the conventions a new screen should follow. |
| `docs/roadmap.md` (this file) | Why the work was done, in what order, and which decisions still bind future work. |

## Where it started

The CRM is meant to combine Perfex CRM, Kitchen.co and Linear, with the tasks part
feeling like Linear. A review on 2026-09-30 (version 0.7.0) found a solid base
(per-project statuses, priorities, labels, sub-tasks, comments, activity, time
tracking, drag and drop with a persisted order, layered permissions) but a daily
experience closer to Perfex or Plane than to Linear:

- the list and the board were two separate pages with different filtering;
- nothing could be changed from a row or a card, only from the drawer;
- no keyboard, no search across the app, no quick way to create a task;
- statuses were grey badges with a "counts as done" flag;
- a task id was the first four letters of the project name plus a global number.

Who it is for shaped the scope: the owner and a small team. There is no client
portal, and logged time is not linked to invoices (asked on 2026-09-30, answered
"not for now").

## The four points

Each point was planned on its own, delivered as a few pull requests, and reviewed
after implementation; the review fixes are the `x.y.1` releases and the fix PRs
below.

### 1. Unified view (0.8.0)

One Tasks page per project instead of a list tab and a separate board page.

| PR | What |
|---|---|
| #31 | Status types (backlog, unstarted, started, completed, canceled) replacing "counts as done"; status, priority and avatar components |
| #32 | The project Tasks page with a URL-driven list: filters, grouping, sorting, "Show more", a remembered view per person |
| #33 | The board as a second layout of the same page; drops are anchored to a card (`after_id`), not to a visible index |
| #34 | My Tasks on the same machinery, grouped by project, open tasks only by default; release 0.8.0 |

Decisions that still hold:

- **The URL is the source of truth for a view.** `TaskViewSpec` (`apps/tasks/viewspec.py`) reads and validates it; the list and the board both use it. A bare URL never renders: it redirects to the saved view or the default, so every history entry says what it showed.
- **A view is remembered only when the toolbar changed it.** A shared link, a refresh or a search does not overwrite what a person last chose.
- **The page's shape lives on `TaskViewOptions`** (layouts, groupings, defaults), so a page that is not a project (My Tasks) uses the same spec.
- **Statuses stay per project; the status type is the cross-project layer.** My Tasks filters and groups by type. Making statuses global was considered on 2026-10-01 and rejected: it would flatten projects with different workflows and need a merge of every project's columns. Priority was already global.
- **The status filter is stored as what is hidden**, so a status added later shows up in saved views by itself.
- **The whole page is always rendered and the client selects the fragment** (`hx-select`), the convention already used by the list pages.

### 2. Speed (0.9.0, 0.10.0)

Working without opening the drawer for every change.

| PR | What |
|---|---|
| #35 | A template comment that printed on the page; a test that catches multi-line `{# #}` |
| #36 | Status, priority and assignee changed straight from a row or a card, through one floating menu |
| #37 | Keyboard: a selection moved with J / K or the arrows, Enter, `/`, C, S / P / A, `?`, one Escape dispatcher |
| #38 | The new-task drawer made fast: status picker, "Create more", prefills, a "+" on group headers |
| #39 | Review fixes (the list refresh lost when the drawer closed, Escape on collapsible sections, scroll after a drag); release 0.9.0 |
| #40 | The Ctrl/Cmd+K palette: search tasks, projects, clients and pages; release 0.10.0 |

Decisions that still hold:

- **The create drawer was kept** rather than replaced by a compact modal, because it matches the task drawer. It was made fast instead.
- **One menu element for the whole page**, opened by a delegated listener, instead of a dropdown per row.
- **The existing update endpoints are reused**; their `HX-Trigger` events (`taskChanged`, `taskStatusChanged`) refresh the view.
- **One Escape handler** (`static/js/keys.js`) with a fixed order of layers. A new popover registers as a layer or uses the dropdown pattern (`open` plus `@click.away`).
- **Closing the drawer empties it, but not at once**: a detached request source loses its `HX-Trigger` events.
- **The palette searches and jumps; it has no actions.** Each section shows only what a person may open and only if they have that module.
- **Own scripts are plain files in `static/js/`**, loaded by a blocking tag; state that templates read stays inline.

### 3. Depth (0.11.0 to 0.15.0)

What a task holds and what happens around it.

| PR | What |
|---|---|
| #41 | Task ids per project: a stable key chosen in project settings plus a per-project number (`CUST-12`) |
| #42 | Markdown in descriptions and comments, with Write / Preview |
| #43 | Comments can be edited and deleted; Activity also records title, description, estimate and label changes |
| #44 | In-app notifications and an Inbox: assigned, mentioned, comments on tasks you follow |
| #45 | Review fixes (GitHub references written `#CUST-12`, file names turned into links, mention matching); release 0.14.1 |
| #46 | Closed tasks archive themselves after 14 days |

Decisions that still hold:

- **URLs and DOM ids stay on the primary key**; the id shown to people is `key-number`. Existing tasks were renumbered once in creation order.
- **The task number is allocated in `Task.save()`** under a lock on the project row, and a full `Project.save()` never writes the counter back.
- **Markdown is rendered by one filter** (`apps/tasks/templatetags/task_markdown.py`): raw HTML is escaped, images are not rendered, and only text that says it is a link becomes one. That filter is the only place user text becomes markup.
- **Notifications are in-app only.** Email was deferred: there is no background worker, and sending during the request would slow every action.
- **A notification is created only where an author is known** (the task signal and `add_comment`), so imports and syncs do not flood anyone. Who may still see the task is checked when the Inbox is read.
- **Following a task** means being its assignee, its creator or someone who commented, read from Activity. There is no "created by" field and no subscription table. A notification when a task is closed was left out.
- **Archiving is computed, not scheduled.** `closed_at` is kept by a rule in `Task.save()` (and `Status.save()` for a type change); archived means closed for longer than `TASK_ARCHIVE_AFTER_DAYS`. The period is one setting for the app, not per project. Archived tasks leave the boards and default lists and stay in search, counts and "Show archived".
- **Every data migration has a way back**; a test migrates the apps backwards and forwards.

### 4. Time tracking in the task (0.16.0 to 0.18.1)

Time moved out of the task body into a property and into Activity.

| PR | What |
|---|---|
| #47 | Durations as text (`1h 30m`, `90m`, `1.5h`, `1:30`), the estimate stored in minutes, one time zone for the app |
| #48 | One "Time" property (logged / estimate, a bar, Start / Stop, Log time by duration and date) and a timer button in the task header |
| #49 | Work log in Activity: time entries in the timeline, with All / Comments / Work log tabs and totals per person |
| #50 | Review fixes (Work log totals after an edit, note-only edits, the property menus of the full page); release 0.18.1 |

Decisions that still hold:

- **One module for durations** (`apps/tasks/durations.py`). A number without a unit means hours in the estimate and is refused when logging time, so "15" cannot log fifteen hours.
- **One time zone for the whole app** (`TIME_ZONE`, default `Europe/Bucharest`), chosen over a zone per person on 2026-10-01.
- **Every entry is shown and edited as a day plus a duration.** A timer keeps its real start, but clock times are not shown and cannot be edited.
- **Time entries are merged into Activity when it is read**; no activity row is written per entry, so there is nothing to keep in step on edit or delete.
- **The Activity tabs only hide rows on the client**, and a task always opens on "All", so a notification never leads behind a tab that hides its comment.

## After the roadmap

| PR | What |
|---|---|
| #51 | The Inbox as a mail-style split view: notifications on the left, the whole task on the right; release 0.19.0 |

The Inbox is a stream of what happened, not a list of work, so it deliberately
does not look like My Tasks. The task in the pane is the drawer's template
rendered in the page (`render_task_drawer(..., embedded=True)`); the lists inside
it are named per task so a drawer opened over it does not share ids.

## How the work was run

- **Every pull request bumps `VERSION` and adds its section to `CHANGELOG.md`** (a rule from 2026-10-01; the earlier PRs of points 1 and 2 were released together as 0.8.0 and 0.9.0).
- **A plan per point, written before implementation**, with the questions that needed an answer asked first and the design checked against the code by a second reader.
- **An independent review after each implementation**, with the findings fixed and covered by tests before the next point started.
- **Checked in a browser, not only by tests**, on a migrated copy of the dev database.

## Not done

None of this is committed to; it is what was deferred or noticed along the way.

Small:

- Attachments cannot be deleted.
- Sub-tasks cannot be renamed or reordered.
- The app sidebar does not collapse, so narrow screens get tight (the Inbox most of all).
- Releases after 0.6.0 have no git tag.

Larger, each needing its own plan:

- Email notifications, or a daily digest (needs a way to send in the background).
- Sub-tasks as full tasks (assignee, status, due date).
- Milestones or cycles, and relations between tasks (blocks, blocked by).
- Bulk actions on the list.

Considered and declined, with the date:

- Linking logged time to invoices: not for now (2026-09-30).
- A client portal: out of scope, the tool is for the owner and a small team (2026-09-30).
- Global statuses: rejected in favour of status types (2026-10-01).
- A time zone per person: one app-wide zone instead (2026-10-01).

To check on real data rather than build:

- Descriptions imported from Perfex are probably HTML and show their tags as text since markdown (0.12.0).
