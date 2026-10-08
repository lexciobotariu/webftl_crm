# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.23.1] - 2026-10-08

### Changes
- Finished and cancelled projects are no longer offered on a new invoice line; a line that already names one keeps it
- The search palette leaves out finished and cancelled projects and archived clients, as the projects page and the client list do

## [0.23.0] - 2026-10-08

### Features
- **Projects have a start date and a deadline.** Both can be set in the New Project drawer and in project settings; a deadline before the start date is refused. The overview shows them, and the project lists show "Due <date>" under an open project's name, in red once it is overdue
- **Billing type per project: Hourly or Fixed price.** Hourly keeps the hourly rate. Fixed price takes the amount the client pays for the whole project, in the client's currency. Time on a fixed-price project is shown in hours only on the time page and in its CSV, without an amount. The overview shows how the project is billed

### Migrations
- `projects.0019` adds the start date, deadline, billing type (every existing project is Hourly) and fixed price

## [0.22.0] - 2026-10-08

### Features
- **Projects have a status:** Active, On hold, Finished or Cancelled, set in project settings and shown on the overview. The projects page lists open projects (Active and On hold); "Show finished and cancelled" lists the rest. The client page still lists every project, with its status when it is not Active, and the dashboard counts open projects
- **Project descriptions and notes use Markdown,** with the same Write/Preview editor as task descriptions, and are shown formatted on the project overview and in the note drawer

### Changes
- **One New Project drawer.** "Add Project" on the projects page opens the same drawer as on a client page, with a client picker; the separate create page is gone (an old link opens the projects page with the drawer open)
- **Task counts agree everywhere.** The project list, the client's projects tab and the project overview count the tasks the person can see, without archived ones, the same number the Tasks page starts from. The overview shows archived tasks as "+N archived"
- **New permission presets start without Salaries and Invoices.** They are ticked on purpose when a preset should see money. Existing presets keep what they have
- The client To-Dos tab says "Only you see these": client to-dos are personal
- The Markdown preview works for everyone signed in, not only people with the tasks module, since notes and projects use it too

### Fixes
- Deleting a person no longer deletes the time they logged. Someone with logged time (or salary records) cannot be deleted; the confirmation says so and offers no Delete button, and they are deactivated instead
- A project with logged time or on an invoice cannot be deleted; settings say to set it Finished or Cancelled instead. A client whose projects have logged time cannot be deleted either and is archived instead

### Migrations
- `projects.0018` adds the project status (every existing project is Active)
- `accounts.0013` makes Salaries and Invoices off by default for new presets (no existing row changes)
- `tasks.0025` protects logged time from a user delete

## [0.21.0] - 2026-10-08

### Features
- **Clients can be archived.** Archive (and Restore) sits next to Edit on the client page. An archived client leaves the client list, the dashboard count and the client pickers for new projects and invoices; its projects, invoices, notes and history stay, and "Show archived" on the client list finds it again
- **A sent invoice can be cancelled.** It keeps its number and lines, shows as Cancelled, owes nothing and takes no payments. An invoice with payments has to have them removed first, and cancelling cannot be undone
- **A payment recorded by mistake can be removed** from the invoice page (with the invoices edit permission)
- **GitHub sync can be switched on in project settings,** under the repository address, instead of only in the admin

### Fixes
- Deleting a client no longer deletes its invoices and payments with it: a client with invoices can only be archived. A client without invoices can still be deleted by an admin, and the confirmation now names everything that goes with it (projects, tasks, logged time, notes, to-dos)
- Creating a project only offers, and only accepts, active clients the person can see. The "Add project" drawer on a client page no longer works on a client that is hidden from that person
- A project's repository address must be a web address (http or https). An address saved earlier that is not one is no longer shown as a link
- A project name over 255 characters or an address over 200 is refused with a message, on the client page drawer and in project settings, instead of a server error
- `?client=` with something other than a number on the project list is ignored instead of a server error
- An invoice with no lines, or a total of zero, can no longer be marked sent (it used to show as Paid straight away)
- Payments can only be recorded on a sent invoice; a draft is not owed yet
- A client's name on project pages links to the client only when that person can open the client, instead of leading to a "not found" page. Someone who may edit every project now also sees every project in the list
- The old free-text notes of a client, no longer editable since the notes module, are shown read-only on the profile so their text is not lost
- The client delete confirmation shows names with an apostrophe correctly
- The client and project lists count projects and tasks in one query instead of one per row
## [0.20.0] - 2026-10-08

### Changes
- The task list can be ordered **Manual**: the order the cards were dragged into on the board. It is the default when the list is grouped by status, so the list and the board show the same order. Other groupings still default to Priority. My Tasks does not offer it, since the order belongs to one project's columns
- **Show empty groups** in the Display menu lists the groups that have no task, with a count of 0, so an empty status no longer disappears from the list. It is on by default when grouping by status and off for the other groupings. Changing "Group by" also moves the order and this switch to the new grouping's defaults, unless you had changed them yourself
- The list search finds a task by its id as well as its title: "CUST-12", "cust-12", "12" or "#12"
- Anyone who can see a task can now comment on it, not only people who may edit it. Changing or deleting a comment is still for its author or an admin
- A task whose status changes from the drawer or the quick menu lands at the top of its new board column, the same place a new task goes. Dragging still puts it where it is dropped
- Board column headers show the status icon, as the list's group headers do
- New keys on a selected task: **I** assigns it to you, **D** sets the due date (Today, Tomorrow, Next week, In two weeks, or any date), **Shift+L** picks labels, **Ctrl/⌘+.** copies its id and **Ctrl/⌘+Shift+,** copies its link. "?" lists them
- A quick edit (priority, assignee, labels, due date) now refreshes only the row or card it changed, so edits feel instant on long lists. The whole list still reloads when the task moves to another group or place, leaves the filter, or changes status
- **Subscribe / Unsubscribe** next to a task's activity: unsubscribe to stop comment notifications on a task you were assigned, created or commented on, or subscribe to one you have no part in. Mentions still reach you
- **Properties** in the Display menu choose which columns a list row shows: ID, Labels, Due date and Estimate (plus Project on My Tasks). The choice is kept in the URL and the saved view
- Sub-tasks can be renamed (click the title) and dragged into another order by people who can edit the task
- Tasks have a **Billable** switch (on by default) and projects an **Hourly rate** (Settings > General), in the client's currency. The time page splits billable from non-billable time and shows what the billable time is worth. Invoices are not affected
- Tasks have an optional **Start date** in the drawer, and the Filter menu can show only tasks already started or only those not started yet
- The time page can show a **Month** as well as a week, **group** the totals by project, client or person (person for those who see everyone's time), and **download a CSV** of the entries or of the grouped totals

### Migrations
- `tasks.0023_task_subscription` adds the table behind Subscribe / Unsubscribe. It only creates a table, nothing is rewritten
- `projects.0017_project_hourly_rate` adds the empty hourly rate to projects
- `tasks.0024_task_billable_start_date` adds Billable (every existing task becomes billable) and the empty start date to tasks

### Documentation
- `docs/ui-patterns.md` records the rules above, why rows show at most three labels (then "+N") while cards show them all, and how billing, start dates and the time page fit together

## [0.19.2] - 2026-10-08

### Fixes
- People who may only view a task now see it read-only in the drawer, on the full page and in the Inbox: the title, description, properties, sub-tasks and labels show their values, with no menus, no "Add sub-task", no "Attach" and no comment box that would only answer "forbidden". Empty values read "No due date", "No labels" and so on instead of "Add …"
- The board offers dragging only to people who may edit the project's tasks
- Anyone who may edit a task can add sub-tasks to it, not only people who may create tasks. People who may create tasks but not edit this one can still add a sub-task, but not tick or delete it
- A title longer than 1,000 characters is refused with a message instead of a server error, and the title field stops at that length
- Saving the edit form inside the drawer shows the full drawer again, with its assignee and label menus filled
- Reordering cards within a board column no longer changes a task's "Updated" time, so "Order by: Updated" stays put after a tidy-up. Moving a card to another status still counts as an update
- Adding, ticking or deleting a sub-task updates the "2/5" count on its board card straight away
- Due dates in another year show the year in the list and on cards ("Jan 05, 2027"), and the activity line for a due date change always includes it
- Expired timers are closed once per request instead of up to three times when a task opens
- The "+" on a board column shows when it gets keyboard focus, and has a label for screen readers

## [0.19.1] - 2026-10-02

### Documentation
- `docs/roadmap.md` records the tasks roadmap: the four points (unified view, speed, depth, time tracking), the pull requests and versions that delivered each, the decisions that still hold, and what was left out or declined. The README links it next to the changelog and the UI patterns

## [0.19.0] - 2026-10-02

### Changes
- The **Inbox** now works like a mail client: notifications in a column on the left, on three lines each (who and when, the task, what happened), and the one you pick open on the right with the whole task, so you can reply, change its status or log time without leaving the Inbox. It no longer looks like My Tasks, because it is a stream of what happened rather than a list of work
- Moving with J / K opens the next or previous notification and marks it read, as in a mail client; the count in the sidebar and on the Unread tab follow at once
- For a comment or a mention, the pane scrolls to that comment and highlights it
- Tabs show All, Unread or Mentions; notifications are separated by day (Today, Yesterday, This week, Older); "Show more" loads 50 at a time. On the Unread tab the notification you have open stays in the list until you move on
- The address names the open notification, so a reload or a shared link opens the same one; opening it from a link marks it read only once the page has loaded

### Features
- Mark a notification unread again, or delete it, from the bar above the task; deleting opens the next one
- Keyboard in the Inbox: J / K to move, Enter to open, E to mark read or unread, Backspace or Delete to delete, ? for the list, Esc to close the notification
- On a narrow screen the open notification covers the list, with a back button
- Moving to another notification, closing or deleting one asks first when a reply or an edit is being written in the pane

### Fixes
- Sub-tasks and attachments added in the drawer land in that task's own lists when another task is open in the page under it (the Inbox pane)
- The "Add sub-task" button no longer logs a script error on every click

## [0.18.1] - 2026-10-02

### Fixes
- Editing a time entry in the Work log updates the totals above it straight away, instead of leaving the old duration until the next refresh
- Changing only the note of a time entry leaves its times alone: a timer of 29m 45s is no longer rounded to 30m, and an entry longer than a day (an import) can still have its note edited
- A refused edit of a time entry keeps the date that was typed
- A day with a mistyped year (a two-digit year becomes the year 25) is refused instead of logging time in the distant past
- The estimate on the new-task and edit forms shows what was typed and can be cleared again
- A duration written with dozens of digits is refused with a message instead of a server error
- The Work log no longer says "No time logged yet." next to an "Others" total, shows two people with the same name as two lines, and cannot show a phantom "Others <1m" while a timer runs
- A failed request no longer closes the Log time popover and discards what was typed
- On the full task page, the State, Assignee, Priority and Labels menus open inside the Properties sidebar instead of running past the edge of the window and being cut off

## [0.18.0] - 2026-10-01

### Features
- Time you log now appears in a task's **Activity**, in order with comments and changes: "Lex logged 1h 30m — note". A time entry sits where it was logged, so an entry logged now for yesterday is next to today's activity
- Activity has **All / Comments / Work log** tabs. Work log opens with each person's total (and "Others" for time you cannot see, so the sum matches the Time property). Every task opens on All; writing a comment from Work log returns to All
- Edit and delete a time entry right in Activity, like a comment. A running timer shows as "timer running"
- The activity list also refreshes when a timer starts or stops, or time is logged, edited or deleted

### Changes
- The "Time" section in the task body is gone: its entries live in Activity, and Start/Stop and Log time are in the Time property and the task header
- Time entries record when they were logged. Existing entries are dated by when they ended, and Perfex imports by their finish time

## [0.17.0] - 2026-10-01

### Features
- A single **Time** property in a task shows `2h 15m / 4h` with a thin progress bar (going over is written out: "Over by 30m"), and holds Start/Stop, **Log time** and the estimate, which is edited by clicking it
- A Start/Stop button in the task header (drawer and full page), for people who can log time
- Time is logged as **a duration and a date** (plus a note): `45m` for yesterday, `1h 30m` for today. A day cannot be in the future; the duration is 1 minute to 24 hours. Logging early in the morning no longer fails because the end would be "in the future"
- Time lists show a date and a duration, never start and end times

### Changes
- Editing a logged entry changes its duration, date and note. A timer keeps its real start; the end follows the duration
- My Week has Date and Duration columns in place of Start and End
- The Time section in the task body is now just the list of entries; Start/Stop and logging moved into the property
- Logging from the property does not close the task drawer
- Entries from the same day keep a steady order

## [0.16.0] - 2026-10-01

### Features
- Estimates and durations are written as text with hours and minutes: `1h 30m`, `1h30`, `90m`, `1.5h` or `1:30`. A bare number is hours in the estimate field; logging time asks for a unit so `15` can't log 15 hours
- Estimates can be set in minutes. Until now the field said "Hours" and accepted halves, but the server refused them
- A wrong estimate gets a message in the popover and in the create drawer, instead of closing silently
- One time zone for the whole app, `TIME_ZONE` (default `Europe/Bucharest`), set in `.env`

### Changes
- **Times on screen move from UTC to Bucharest time** (activity, comments, invoices, My Week). Stored dates and times do not change
- "Today" follows that time zone: a task due today is no longer overdue from 02:00 or 03:00 at night, and the day lists and week no longer flip at that hour
- Durations read the same everywhere: `1h 30m`, `45m`, `2h`, and `<1m` under a minute. Totals that read `3h 05m` now read `3h 5m`
- The estimate is stored in minutes (`Task.estimate_minutes`); existing estimates keep their value, so 4h stays 4h. An estimate of 0 hours becomes "no estimate"

### Fixes
- Saving the full task form no longer reads the estimate back as a different number

## [0.15.0] - 2026-10-01

### Features
- Done and canceled tasks archive themselves 14 days after they were closed: they leave the boards and the default lists, and stay in search, the project counts and the drawer
- "Show archived" in the Filter menu (list and board) brings them back; the count row says "N archived · Show" next to "hidden by filters", and a Done column holding only archived tasks says so
- An archived task shows "Archived" in its drawer; reopening it brings it back
- "Show all" on My Tasks includes archived tasks

### Changes
- **On deploy, tasks closed more than 14 days ago disappear from boards and default lists.** Existing closed tasks are dated by their last status change, or their last update when there is none
- Changing a status's type to completed or canceled (or back) closes or reopens the tasks in it, from the project settings and from the admin alike
- Tasks imported from Perfex are dated by their finish date, so old finished work archives at once

### Fixes
- A GitHub issue sync no longer moves every synced task back to the first status; the first status only applies to a new issue, and reopening an issue on GitHub reopens its task
- A list whose tasks are all archived says so and offers to show them, instead of "No tasks yet"

## [0.14.1] - 2026-10-01

### Fixes
- A commit or pull request that writes a task as `#CUST-12` is linked like one that writes `CUST-12`, and a message naming several tasks links to the first one that exists
- File names such as `manage.py`, `README.md` or `deploy.sh` in a description or comment are no longer turned into links; a link needs `http://`, `https://` or an email address
- Mentioning `@Alex Pop` no longer also notifies Alex when he had been picked in the same comment earlier
- Losing access to a project withdraws an unread "assigned you" notice along with the assignment, so it does not come back if the person is added again
- Saving the full task form no longer logs "updated the description" when only the whitespace at its ends differed
- The description editor's Save button works again after a save was refused for being too long
- Two projects created at the same moment with the same name prefix no longer fail on the derived key

## [0.14.0] - 2026-10-01

### Features
- An Inbox (sidebar and command palette, for people with the Tasks module) lists what happened on your tasks: being assigned, being mentioned, and comments on tasks you follow; unread first, then earlier ones
- Clicking a notification opens the task in the drawer and marks it read; "Mark all read" clears the list
- Typing `@` in the comment box lists the people who can see the task; picking one mentions them, and a mention takes the place of the "commented" notification
- Following a task means being its assignee, its creator, or someone who commented on it; your own changes never notify you
- The sidebar shows the unread count, refreshed when you come back to the tab

### Changes
- Notifications are only created by a person's action, so imports and GitHub syncs do not send any; a notification disappears from the Inbox when you lose access to its task or when its comment is deleted
- Several comments on one task while you have not looked collapse into one notification showing the latest

## [0.13.0] - 2026-10-01

### Features
- Comments can be edited and deleted by their author (while they can still edit the task) or by an admin; an edited comment says so, and editing or deleting changes only that comment, not the whole list
- Activity also records title changes, description updates ("updated the description", without a diff), estimate changes, and labels added or removed from the drawer or the edit form

### Changes
- New activity rows appear in the open drawer right after a title, description, estimate or label change
- The activity list loads every author in one query instead of one per row

## [0.12.0] - 2026-10-01

### Features
- Task descriptions and comments are written in Markdown: bold, italics, lists, code, quotes, headings, tables and links; bare URLs become links, and a single line break is kept, so existing text reads the same
- The description editor and the comment box have Write and Preview tabs; Escape in Preview goes back to Write instead of closing the drawer, and Ctrl/Cmd+Enter saves or posts
- The description has an explicit edit button (also reachable with the keyboard)

### Changes
- Clicking a link in a description opens the link instead of starting an edit
- Raw HTML typed into a description or comment is shown as text and images are not embedded. Links open in a new tab without access to the opener; a link with another scheme (`javascript:`, `data:` and so on) loses its target
- Descriptions and comments are limited to 100,000 characters
- Descriptions imported from Perfex that contain HTML will show their tags as text

## [0.11.0] - 2026-10-01

### Features
- Task ids count per project: each project has a key (derived from its name, for example `CUST`) and its tasks are numbered `CUST-1`, `CUST-2`, ... in the list, on board cards, in the drawer, on the full page and in the command palette
- The key can be changed under project Settings (2 to 6 capital letters or digits, starting with a letter, unique across projects); renaming the project no longer changes its task ids
- Search finds `CUST-12` as task 12 of the project with that key, and a plain `12` as task 12 of any project you can see
- GitHub commits and pull requests that mention `CUST-12` (the exact key, as a whole word) link to that task; the older `#TASK-<id>` form still works

### Changes
- **Every task gets a new id.** Existing tasks are numbered per project in the order they were created, so `ERP-285` may become `ERP-12`. Task links and URLs are unchanged
- Search no longer ignores the prefix of a task id: an unknown key finds nothing
- In the admin, a task's number and a project's task counter are read-only

### Upgrade notes
- The migration runs when the new container starts; stop the old instance from creating tasks while it runs

## [0.10.0] - 2026-10-01

### Features
- A command palette: Ctrl/Cmd+K (or the Search button in the sidebar) searches tasks by title or id, projects, clients and pages, shows only what the person may open, and opens a task in the drawer on the page they are on

## [0.9.0] - 2026-10-01

### Features
- Status, priority and assignee can be changed straight from a task row or board card, without opening the drawer; the list and the board keep their scroll position after an edit or a drag
- Keyboard on the Tasks pages: `J` / `K` or the arrows move a selection through rows and cards (`H` / `L` between board columns), `Enter` opens the task, `/` searches, `C` creates a task, `S` / `P` / `A` change status, priority and assignee on the selected row, and `?` lists the shortcuts
- The new-task drawer is faster: the title is focused when it opens, Enter or Ctrl/Cmd+Enter creates the task, and a double submit makes one task
- The new-task drawer has a status picker, so the status it was opened with can be changed before creating
- "Create more" in the new-task drawer keeps it open on a fresh form with the same status, assignee and priority (remembered between visits)
- A "+" on each status, priority and assignee group header in the Tasks list opens the new-task drawer with that value filled in
- Escape closes one thing at a time: shortcut list, quick menu, dropdown, drawer, then the selection; collapsible sections such as the ones in the permission preset drawer are not dropdowns and stay open

### Changes
- Closing the drawer empties it, so it stops fetching activity for a task nobody is looking at
- Setting a task's priority to a value that is not one of the choices is refused instead of saved
- Picking the status a task already has no longer moves its card to the end of the column

### Fixes
- Opening the new-task drawer with a status that is not a number no longer fails with a server error, and neither does changing a task's status with one
- A template comment that spanned two lines was printed as text on the Tasks and My Tasks pages; a test now catches multi-line `{# #}` comments

## [0.8.0] - 2026-10-01

### Features
- Statuses have a type (backlog, unstarted, started, completed, canceled) instead of a "counts as done" flag; canceled work no longer counts as active or overdue, and the settings page has a type select per status
- Status, priority and unassigned icons follow Linear's design (Tabler and Material Design Icons SVGs, inlined)
- Each project has one full-width Tasks page at `/projects/<pk>/tasks/` with a List/Board toggle, shared filters (status, priority, assignee, labels), search, and — in the list — grouping, sorting and "Show more"
- The Tasks page state lives in the URL, so views can be shared and Back works; the last view you used on a project is remembered per person
- My Tasks uses the same URL-driven list as the Tasks page: grouped by project (or status type, or priority), filtered by status type and priority, searchable, with "Show more"; it shows only open tasks until you ask for finished ones, and remembers your last view
- On the board, dropping a card under active filters places it under the card it landed on instead of at a position counted only among visible cards
- Time tracking on tasks: one running timer per person with a 12-hour automatic stop, manual start and end entries, the logged total shown under Estimate, and a My Week page
- Invoices: an invoice belongs to one client, mixes that client's projects with free-text lines, keeps a bill-to snapshot, and derives its status from send state, payments and the due date; clients carry a billing name, email and tax id
- Company settings, a fixed currency per client, and a choice of where the currency symbol sits (snapshotted on invoices)
- Permission presets are grouped into module cards, with view-all, create and edit flags for clients, projects, tasks, notes, salaries and team
- Each project has a Team screen that lists and edits who has access to it
- Perfex SQL import; task titles can be up to 1000 characters
- A light theme, chosen globally in Settings; the dark theme is retinted to the Linear palette

### Changes
- `/projects/<pk>/kanban/` now redirects to the Tasks page in board layout
- The project Tasks tab and its saved status/priority filter are replaced by the Tasks page; filters saved on the old tab reset once
- My Tasks no longer pages its list or filters statuses by name; its saved status/priority filter resets once and `/tasks/my/filter/` is gone
- Editing a task's assignee, priority, due date, estimate, labels or title in the drawer refreshes the list behind it, and on My Tasks the Assigned Tasks count with it
- Client and project section menus sit on the left, and list tables sit in cards

### Fixes
- Board columns are ordered by the status order even when the database returns them differently
- Permission checks that leaked data or disagreed between a list and its detail page now apply the same rule

### Infrastructure
- A Dokploy compose file for deployment; database migrations run when the container starts

## [0.7.0] - 2026-08-31

### Features
- Kanban cards can be reordered within a column, not just moved between them — the drop position is persisted and survives a reload
- Statuses can be marked "counts as done" from project settings; project stats derive "Completed" and "Active" from that flag instead of matching status names
- Empty states, permission badges, and the drawer open/close handlers are now shared components instead of copy-pasted markup
- Team members can be added from inside the app: admins get an "Add Member" drawer that sets name, email, role, preset and an initial password, so adding people no longer requires Django admin (and therefore `is_staff`) access

### Fixes
- Deleting a project or a client no longer 500s when its tasks reference a status (`Task.status` uses `RESTRICT` rather than `PROTECT`)
- Validation errors in the task-create and client create/edit drawers are rendered instead of being swallowed by HTMX; typed values are kept
- Creating a task from the project Tasks tab or the dashboard now refreshes those lists
- Editing a client from the detail page refreshes the profile panel and the notes count
- Note creation through the client/project drawers works again — the form now assigns the parent before model validation runs
- Last-admin guards actually lock now — `select_for_update().count()` emitted no `FOR UPDATE`, so two concurrent demotions could both succeed
- `preset_create`, `status_create`, `task_update_assignee`, `task_update_due_date` and the note drawers return errors instead of 500s on duplicate names, non-numeric ids, impossible dates, and missing parents
- Task assignee dropdowns on task detail, the full-page view and the assignee update endpoint are scoped to project members
- `notes_visible_to_user` now applies the project-membership check, matching `can_view_note`
- Notes list and detail render "deleted user" where the modifying user has been removed

### Changed
- Todo, subtask, status-visibility and status-done toggles run inside a transaction with the row locked
- List refreshes re-fetch the current URL, so filters and pagination survive; the count pill and pagination moved inside the refreshed region
- HTMX error toasts cover network and target errors, and show a generic message for 5xx instead of the raw response body
- All CDN scripts are pinned to exact versions with Subresource Integrity; `@alpinejs/collapse` added (`x-collapse` was previously a no-op)
- Signup is closed; the Team page's "Add Member" button opens the in-app create-member drawer rather than the allauth signup page or the Django admin
- The Team list count pill and pagination moved inside the refreshed region, so creating a member updates both without a reload

### Infrastructure
- The unique-constraint migrations de-duplicate pre-existing data before adding the constraint, instead of failing mid-migrate
- `tasks.0005_phase_c` copies any legacy `Comment` rows into `TaskActivity` before dropping the table, so hand-entered admin data on existing installs is not lost
- README: the testing section installs `requirements-dev.txt`, which the install steps do not cover
- CI: valid Fernet key, `SECURE_SSL_REDIRECT=False`, `manage.py check`, and a `collectstatic` step so templates can render under `DEBUG=False`
- Docker: `collectstatic` runs with build-only secrets so the static manifest is generated, the image runs as a non-root user, gunicorn gets explicit workers/timeout, and `CHANGELOG.md` is no longer excluded (the in-app changelog page read it at request time)
- Settings: optional `SECURE_PROXY_SSL_HEADER`, and an explicit `EMAIL_BACKEND` is required outside `DEBUG` rather than silently discarding mail
- `.env.example` documents every supported variable
- Test suite is green on a fresh database and on `--reuse-db`; `ruff check .` is clean

## [0.6.0] - 2026-03-25

### Features
- Full user CRUD in Team page — admins can edit name, email, role, and permission preset from the user detail drawer
- User deactivation (soft-delete) — deactivated users can't log in or be assigned to new tasks, shown greyed out with "Inactive" badge in team list
- User deletion with two-tier cascade warning — clean delete for users with no data, force delete with itemized count of affected records (todos, notes, comments, attachments, salary, project memberships)
- Consolidated user management into single edit form replacing separate toggle-role and update-preset actions

### Fixes
- Filter inactive users from task assignee dropdowns across all task views (task detail, full page, update assignee)

## [0.5.0] - 2026-03-24

### Features
- Add app-level RBAC with permission presets (Admin, Developer) controlling access to Clients, Salaries, Team, and other sections
- Sidebar dynamically shows/hides navigation links based on user's permission preset
- User detail drawer on Team page for viewing user info and assigning permission presets
- Preset editor UI for creating, editing, and deleting custom permission presets with per-section toggle switches
- Client names shown as plain text (not clickable links) for users without client access in project breadcrumbs, lists, and detail pages
- Client filter dropdown hidden from project list for restricted users
- System presets (Admin, Developer) protected from deletion; presets with assigned users cannot be deleted

## [0.4.1] - 2026-03-24

### Fixes
- Fix note deletion from client profile page failing with HTMX target error
- Show Paid status badge for salary months with bonus payments instead of no badge

## [0.4.0] - 2026-03-24

### Features
- Add My To-Dos section to dashboard showing incomplete todos with title, client, due date, and edit action

## [0.3.0] - 2026-03-24

### Features
- Add status board visibility toggle — managers can hide status columns from the kanban board to reduce clutter
- Hidden tasks badge shows count of tasks in non-visible columns on the board header
- New tasks default to the first visible status when created without specifying one

### Fixes
- Support both Keep a Changelog and release skill section labels in changelog template

## [0.2.0] - 2026-03-24

### Features
- Add unified notes table on client profile showing notes from client and all its projects
- Add changelog page with parsed version history accessible from sidebar
- Add Iconify integration for brand icons (GitHub)

### Fixes
- Remove unreachable duplicate URL route in clients app
- Fix missing GitHub icon on project overview page (Lucide dropped brand icons)

## [0.1.2] - 2026-01-29

### Fixed
- Preserve instance values when editing salary month forms (empty drawer bug)
- Make PaymentForm initialization explicit for new records only
- Resolve HTMX/Alpine.js conflict in edit buttons using htmx.ajax() workaround

### Changed
- Add service layer structure for salaries app
- Refactor views to use service layer (thin controllers pattern)
- Add comprehensive service layer tests

## [0.1.1] - 2026-01-27

### Changed
- Standardize drawer button styling across all modules
- Remove `flex-1` from primary buttons for compact layout
- Add gray transparent background with subtle border to Cancel buttons
- Change notes module from purple to accent color for consistency

## [0.1.0] - 2025-01-27

### Added
- Initial release
- User authentication with django-allauth
- Client management (CRUD operations)
- Project tracking with status workflow
- Task management with assignments
- Todo lists per task
- Notes system for clients, projects, and tasks
- Salary management with monthly payments
- Team management for admins
- GitHub integration support
- Dashboard with overview metrics
