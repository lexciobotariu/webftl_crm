# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
