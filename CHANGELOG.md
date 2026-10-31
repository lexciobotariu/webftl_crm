# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.41.0] - 2026-10-31

**htmx 2 → htmx 4.** The app should work as before; the changes below are what htmx 4 needed. No database migrations, nothing to set in Dokploy. To go back to htmx 2, revert this release alone; the preparation in 0.40.1–0.40.3 stays.

### Changed
- htmx 2.0.11 → 4.0.0 (pinned with SRI). Its settings are in one `<meta name="htmx-config">` in `base.html`: error answers (4xx/5xx) are still shown only in the toast, never put into the page; Back loads the page again (as the task list already did); requests have no time limit, as before (htmx 4 would stop them after 60 seconds)
- htmx 4 passes attributes from a parent element only when they are marked `:inherited`. `<body>` marks the three that every request needs: the CSRF header, the global spinner and `hx-sync="queue last"`
- `hx-sync="queue last"`: a second change made while the first is still saving now waits for it and then saves the latest state. Without it htmx 4 would have kept the second change and dropped any later one, so in the invoice editor a line changed three times quickly would have been saved with its second value (caught by the new browser check)
- `static/js/htmx-events.js` listens to htmx 4's events. The rest of the app is unchanged: same `request:*` / `swap:*` events, and `HX-Trigger` events still fire before the swap, from the element that sent the request, as in htmx 2
- `static/js/morph.js` registered the htmx 4 way; it still uses Alpine's morph plugin, which keeps Alpine state
- Removed attributes htmx 4 dropped (`hx-ext`, `hx-disinherit`, `hx-history`); `hx-disabled-elt` is now `hx-disable` (the Send button in the invoice email drawer)
- The search field on the Tasks page updates the filter badge itself; it used to inherit that from the toolbar
- Two click filters (task row, description) no longer use a `]` inside the filter, which htmx 4 reads as the end of it
- `scripts/htmx_smoke.py`: three more checks (Create more, the CSRF and tab headers, invoice autosave); 24/24 pass on htmx 4

## [0.40.3] - 2026-10-31

Second step towards htmx 4. Nothing changes for people using the app.

### Changed
- New `static/js/htmx-events.js`: the only file that knows htmx's event names and details. It turns them into the app's own events (`request:start`, `request:end`, `swap:before`, `swap:after`, `swap:done`, `response:error`, `request:fail`, `request:config`), which the rest of the JavaScript listens to. htmx 4 renames these events, so the switch will change this one file
- The 55 `hx-on::after-request` / `hx-on::config-request` handlers in the templates are gone (htmx 4 never fires them). Opening the drawer, resetting or hiding a form, emptying a file field and removing an "empty" message after success are now declared with `data-after-success`, `data-after-success-remove` and `data-after-request`; Alpine forms listen to `@request:start` / `@request:end`
- `scripts/htmx_smoke.py` checks four more screens (Add to-do, project labels, Log time, inbox J/K): 21 checks, all passing on htmx 2

## [0.40.2] - 2026-10-31

### Changed
- **Django 5.1.4 → 5.2.18 (LTS, security fixes until April 2028).** Django 5.1 stopped receiving security fixes in December 2025. No database migrations; Django 5.2 needs PostgreSQL 14 or newer (production runs 18)
- `django-htmx` 1.27.0 → 1.29.0 (needs Django 5.2): reads htmx 4's `HX-Source` header as `request.htmx.source`, now used to recognize the task toolbar

## [0.40.1] - 2026-10-31

First step towards htmx 4. Nothing changes for people using the app.

### Changed
- htmx 2.0.4 → 2.0.11, the latest 2.x (bug fixes only)
- The task list recognizes its toolbar both by the header htmx 2 sends (`HX-Trigger`) and by the one htmx 4 sends (`HX-Source`), so saved views keep working through the switch
- Reordering sub-tasks also accepts the ids as one comma-separated value, which is how htmx 4 sends a list
- New `scripts/htmx_smoke.py` (see CONTRIBUTING): a browser check of the htmx screens, run before and after each step of the htmx 4 move. Playwright stays out of `requirements-dev.txt`, like for the screenshots
- The CSRF token is also in a `<meta name="csrf-token">` tag; the description Preview reads it from there instead of from `<body hx-headers>`, which htmx 4 changes

## [0.40.0] - 2026-10-30

### Changed
- **Editing in the task drawer updates only that row** of the list or board behind it, instead of reloading the whole view. The scroll position and the row selected with the keyboard stay put. When the edit moves the task (another group or place, or out of the view), the whole view reloads as before
- **Live updates touch only the rows that changed.** When a colleague or Claude (MCP) edits a task, other open tabs refresh just that row or card. A new task, a deleted task or a new status still reloads the list or board, since rows move and counts change
- **Reloads change only what differs** (Alpine's morph plugin, new script `@alpinejs/morph` 3.17.1): the list or board after an edit, the open drawer and the task page when someone else changes the task. Focus, scroll and open panes survive, and panels hidden by the page no longer reappear after a reload (the cause of the empty box fixed in 0.38.1)

## [0.39.0] - 2026-10-28

### Features
- **Billable when creating a task:** the New task drawer has a Billing switch in Properties, so a task can be created non-billable from the start. It starts on (billable), as before. The full-page edit form has the same switch

### Changed
- "Create more" keeps the Billing choice of the task just created, next to State, Priority and Assignee (kept as before)

## [0.38.1] - 2026-10-28

### Fixed
- **Empty box under the description:** after creating a task with "Create more" on, the fresh drawer showed an empty bordered box under the description (the Preview pane, shown while the Write tab was selected). htmx put the new pane's style back after Alpine had hidden it; the pane now starts hidden on its own. The same could happen to the comment box when a task drawer reloaded by itself

## [0.38.0] - 2026-10-25

### Features
- **Task pages update live.** The task list and board (project and My Tasks), the task page and the open task drawer update by themselves when someone else changes a task: a colleague, Claude through MCP, the GitHub webhook. No more refreshing. The rows and cards that changed light up for a moment. While you are typing, have a menu open, have an unsent comment or are dragging a card, the update waits until you are done, so nothing you type is lost. Your own changes do not reload the tab you made them in; your other tabs follow along

### Changed
- **Server:** the app now runs under ASGI (gunicorn with uvicorn workers) instead of plain WSGI gunicorn, so a page can keep a connection open without tying up a worker. Ordinary pages work as before. Database connections are no longer kept between requests (`conn_max_age` 0), as ASGI requires
- Live messages travel between server processes through Postgres `LISTEN/NOTIFY`: no new service. Setting `REDIS_URL` switches them to Redis pub/sub
- Under `runserver` there are no live updates; the README shows how to run the ASGI server locally

## [0.37.2] - 2026-10-25

### Changed
- **Claude (MCP): how Claude writes in the CRM.** The instructions the CRM gives every connected Claude now say: write tasks and comments in the first person, as the signed-in person (never "Lex asked…" or a retelling of the chat); when the scope changes, update the description and subtasks instead of commenting; comment only for a result, a blocker or a decision colleagues need, usually once when the work is done, without progress notes; write in the task's language. The `add_comment` tool description says the same

## [0.37.1] - 2026-10-25

### Fixed
- **Claude connector address:** Security → Connected apps showed `http://…/mcp`, and the sign-in addresses Claude reads (OAuth metadata), task links returned to Claude and portal emails were built with `http://` too, because the proxy in front of the app forwards the scheme as http. New `ALWAYS_HTTPS` setting (on by default in `docker-compose.dokploy.yml`) makes every link the app builds use `https://`

## [0.37.0] - 2026-10-25

### Features
- **Work on tasks from Claude (MCP).** Add `https://<your domain>/mcp` as a custom connector in claude.ai, the Claude apps or Claude Code. A window opens on the CRM: sign in with two-factor, choose what Claude may do (always read tasks; optionally change tasks and use the timer) and press **Allow**. Claude can then list projects, search and read tasks, create and update tasks (assignee, priority, dates, estimate, billable), move them between statuses, add, remove and create labels, comment, add and tick subtasks, start and stop the timer, log time, and **start work** (take the task, move it to In Progress, start the timer) or **finish work** (stop the timer, move it to Done). It cannot delete anything or see invoices and salaries
- Everything done through Claude uses the person's own permissions and shows **via Claude** in the task activity and work log
- **Security → Connected apps** lists what is connected, when it was last used and what it may do, with **Disconnect**. It also shows the connector address
- **Tasks → Use from Claude** in permission presets, off by default (on in the built-in Admin preset); admins always have it

### Fixed
- Signing in now returns to the page that asked for it (for example a link to a task opened while signed out) instead of always landing on the dashboard

### Security
- OAuth 2.1 authorization server (django-oauth-toolkit 3.4): authorization code with PKCE (S256), access tokens of one hour, refresh tokens rotated on every use with reuse detection, tokens stored hashed and bound to the `/mcp` address, codes valid one minute. Clients register themselves (RFC 7591), but only with Claude's callback addresses or a loopback address, at most 20 registrations per hour per IP. The `/mcp` endpoint refuses tokens in the URL and calls from other websites, and allows 120 calls per minute per connection

## [0.36.1] - 2026-10-25

### Fixed
- **Labels:** adding a label whose name the project already has (in any letter case) now says so instead of failing with a server error

### Changed
- Creating a task, changing several of its fields at once, adding or removing a label, creating a label, finding a task by its id (`CUST-12`) and "start / finish work" are now one service each in `apps/tasks/services.py`, with the same permission checks as the screens. The new-task drawer and the project label form use them. Groundwork for controlling tasks from Claude (MCP); nothing changes on screen

## [0.36.0] - 2026-10-25

### Features
- **Client portal** at `/portal/`. A client contact signs in without a password: they type their email and get a link that works once, for 15 minutes; after that they stay signed in for 30 days in that browser. They see their projects (not cancelled ones), the invoices and estimates that were sent to them with the PDFs and what is still to pay, and the emails you sent them. Internal notes, drafts and cancelled invoices never show
- **Accept or decline an estimate** from the portal. The answer is recorded on the estimate, logged as a note in the client's Messages and emailed to the company email from Settings
- **Portal access** per contact: tick it in the contact drawer (an email is required), then **Send portal invite** on the client's profile. The contact list shows who has access, when they were invited and when they last signed in. Unticking access, changing the contact's email or archiving the client ends their portal session at once

## [0.35.0] - 2026-10-25

### Features
- **Dashboard money row** for people with access to invoices: **To collect** (sent invoices not fully paid), **Overdue**, **Paid this month** (payments recorded since the 1st) and, for those who see everyone's time, **Not invoiced yet** (billable hours on hourly projects with their approximate value). Amounts stay per currency. The first two open the invoice list already filtered
- **Deadlines** on the dashboard: your open tasks that are late or due in the next 7 days, and open projects whose deadline is in the next 14 days or has passed
- **Overdue invoices** list on the dashboard, oldest due date first
- **Two-factor code in six boxes** at sign-in, re-authentication and setup: each digit has its own box, the cursor moves to the next box by itself, Backspace goes back, a pasted or autofilled code fills all boxes, and the form submits when the last digit is typed. "Lost your phone? Use a recovery code" switches to a single field for a recovery code

## [0.34.1] - 2026-10-25

### Fixed
- **Two-factor setup:** the key and QR code stay the same from the first load until setup succeeds. Before, every load of the page (a refresh, a second tab, a browser preload) made a new key, so a phone that scanned the earlier one got "Incorrect code" and a new QR code
- Codes from the 30 seconds before or after are accepted too, for a phone or server clock that is slightly off
- While an admin still has to set up two-factor sign-in, the sidebar shows only Security and Logout instead of links that all lead back to the setup

### Changed
- New task attachments are stored in one folder per task, `projects/<project id>/tasks/<task id>/`, with a short random prefix on the file name, so the bucket is easy to browse and two files with the same name never meet. Files uploaded before keep their place and still open
- Long file names are kept up to 255 characters of path instead of 100

## [0.34.0] - 2026-10-25

### Features
- **Two-factor sign-in:** under **Security** (bottom of the sidebar) anyone can turn on a code from an authenticator app (Google Authenticator, Microsoft Authenticator, 1Password, Authy). Signing in then asks for the 6-digit code after the password
- Turning it on also creates 10 one-time **recovery codes** to show or download, for signing in without the phone. New codes can be created at any time; the old ones then stop working
- **Admins must use it.** An admin without it is taken to the setup page before anything else, and cannot turn it off
- Lost both the phone and the recovery codes: `python manage.py reset_two_factor <email>` removes that person's two-factor sign-in so they can set it up again. As a last resort for admins, `REQUIRE_ADMIN_2FA=False` in the environment lifts the rule

## [0.33.0] - 2026-10-25

### Features
- **Settings > File storage:** keep uploaded files in an S3-compatible bucket (Amazon S3, Cloudflare R2, Backblaze B2, Hetzner, DigitalOcean, MinIO). Enter the endpoint, region, bucket, keys and an optional folder. Saving first writes, reads back and deletes a small test file, and nothing is saved if that fails. The secret key is stored encrypted and never shown again
- While files are still on the server disk in production, Settings warns that they are lost on every deploy
- **Task attachments** now open through the app, which checks that you may see the task. From a bucket you get a short-lived private link; the bucket itself stays private
- Whoever can edit a task can remove an attachment (× on hover). Deleting an attachment or its task also deletes the stored file

### Fixed
- Attachment links no longer 404 in production, and files can no longer be fetched by anyone who has the link
- Files saved on the server disk before a bucket was connected still open
- "No attachments yet" disappears after the first upload
- PDFs, images and text open in the browser; other files (Word, Excel, zip, CSV) download

## [0.32.1] - 2026-10-11

### Changed
- **New task:** the status moved from the header into Properties, as the first row ("State"), the same place it has on an existing task
- **New task:** the description has **Write / Preview** tabs and says "Markdown supported", like the other description fields
- **Time on a task:** Start/Stop and **Log time** are now side by side in the task header. The Time property keeps the logged time, the bar and the estimate, without its own buttons

- **Keyboard shortcuts:** press **?** on any page (outside a text field) for one list of every shortcut, grouped by where it works, with the ones for the page you are on first. It also opens from **Shortcuts** at the bottom of the sidebar, and the search box mentions it. Buttons with a key show it in their tooltip, for example "New task (C)" and "Search (/)"

### Fixed
- Ctrl/Cmd+Enter in a description field submitted the form twice where the form has its own shortcut too

## [0.32.0] - 2026-10-09

### Features
- **Add tasks** on a draft invoice lists the tasks with billable time not yet invoiced (only the invoice project's tasks when it has one, otherwise all of the client's hourly projects), all ticked. Choose **one line per task** (task title, hours, the project's hourly rate) or **one line per project** (hours added up). A project without an hourly rate gets a price of 0 to fill in
- Billed time is linked to its line, so it is never billed twice. Removing the line, deleting the draft or cancelling the invoice frees it again
- Tasks show **Invoiced INV-x** next to Billable, and each Work log entry shows the invoice it is on. Time on a sent invoice can no longer be changed or deleted
- **Invoice project** on the project Overview creates a draft for the project's client, with the project set and due in 30 days. Hourly projects: pick tasks as above. Fixed price: one line for what is left of the price (the fixed price less what is already on its invoices, drafts included)
- A new draft from a project starts with the tax rate of the client's latest invoice
- The project's Time and money card shows billable hours not invoiced yet

### Changed
- **Invoice and estimate editor:** the new line row is now at the top of the lines. Each line has an **Item** and an optional **Description** (longer text, printed under the item on the PDF). **Tax %** moved from the header to the totals, next to Subtotal and Tax

### Migrations
- `invoices.0008` adds the task to invoice lines; `tasks.0026` links time entries to the invoice line that bills them; `invoices.0009` adds the description text to invoice and estimate lines

## [0.31.0] - 2026-10-09

### Features
- **Inline invoice editor.** A draft invoice is edited on its own page, like Perfex: client, project, dates and tax at the top, and the lines as a table where description, quantity and price are typed in place. Every change is saved as it is made and the totals update straight away. A new line is typed in the last row and added with Enter or +; × removes a line. The Edit and Add line drawers are gone. Sent invoices stay read-only
- **Estimates use the same editor**, with Valid until and Notes in the header
- **Optional project on an invoice or estimate.** Pick a project of the client, or leave it empty. Changing the client clears it. It is printed under Bill to on the PDF and named in the email
- Lines no longer have a project select: a line is free text. Older project lines keep their project
- **Project filter** on the invoice list, and an **Invoices** card on the project Overview with its latest invoices, View all and New invoice (client and project filled in)
- Converting an estimate and recurring drafts keep the project

### Migrations
- `invoices.0007` adds the project to invoices and estimates; an existing document whose lines all belong to one project gets that project

## [0.30.0] - 2026-10-09

### Features
- **Estimates.** A new Estimates page (sidebar, under Invoices) with its own numbers, EST-0001 onwards. An estimate has a client, issue date, "valid until" date, tax rate, optional notes (scope, terms) and lines like an invoice: project lines or free text
- **Statuses:** Draft, Sent, Accepted, Declined, Expired (sent, unanswered and past its valid-until date) and Invoiced. Lines and dates can change only while it is a draft. The list filters by status
- **Accepted / Declined** buttons record the client's answer on a sent estimate; Clear answer undoes a mistake
- **Convert to invoice** on an accepted estimate creates a draft invoice with the same client, tax rate and lines, due in 30 days. It can be done once; the estimate and the invoice link to each other
- **Email estimate** sends it with the PDF attached, like invoices: replies go to the company email, emailing a draft marks it sent, and every email is logged on the client's Messages tab and on the estimate
- PDF download and a print page

### Migrations
- `invoices.0006` adds estimates and their lines; `clients.0008` links logged emails to an estimate

## [0.29.0] - 2026-10-09

### Features
- **Recurring invoices.** "Repeat" on an invoice turns it into a template: monthly, every 3 months or yearly, from a chosen date, optionally until an end date. On each date a new **draft** is created for the same client with the template's lines (copied as they are), tax rate and number of days to pay, and the client's current bill-to and currency. Drafts are never sent on their own: check them and use Email invoice
- The template shows when it repeats next, with Change and Stop; each draft links back to its template
- An archived client gets no new drafts. A missed day is caught up on the next run, and running twice never creates the same draft twice

### Configuration
- **Schedule `python manage.py create_recurring_invoices` once a day** (in Dokploy, the app's Schedules tab). Without it no drafts are created

### Migrations
- `invoices.0005` adds recurring invoices and links each draft to the one that created it

## [0.28.0] - 2026-10-09

### Features
- **Messages tab on each client.** One log per client with internal notes (Markdown, optionally tied to one of the client's projects) and every email sent to the client, logged automatically with its recipients and whether it went out. Notes are deleted only by their author or an admin; logged emails stay
- **Email invoice.** The invoice page has an "Email invoice" button that opens a drawer with To (prefilled from the bill-to email), Subject and Message (prefilled with a short summary: number, total, what is still to pay, due date). The invoice goes as a PDF attachment and replies go to the company email from Settings. Emailing a draft marks it sent; if the email fails, it stays a draft
- **Send reminder.** For a sent invoice that is still owed, a "Send reminder" button opens the same drawer with reminder wording ("was due on ... and is still open" once overdue)
- **Emails card on the invoice** lists every email and reminder sent for it, failed ones in red with the reason
- **PDF download** on the invoice page and the print page

### Configuration
- **Email goes through Resend** when `RESEND_API_KEY` is set; leave `EMAIL_BACKEND` unset. `DEFAULT_FROM_EMAIL` (for example `WebFTL <facturi@example.com>`) must be on a domain verified in Resend. Quotes around either value are optional
- `docker-compose.dokploy.yml` passes `RESEND_API_KEY` to the container; the Docker image installs Pango, HarfBuzz and DejaVu fonts for the PDFs
- New dependencies: `resend`, `weasyprint`

### Migrations
- `clients.0007` adds the client message log

## [0.27.0] - 2026-10-09

### Features
- **The invoice list has filters:** status (Draft, Outstanding, Overdue, Paid, Cancelled), client and issue date (this month, last month, this quarter, this year, last year). Outstanding means sent and still owed, overdue included
- **Totals above the list,** per currency, for everything that matches the filters: invoiced (sent and not cancelled, with tax), outstanding and overdue. Amounts in different currencies are never added together
- **The invoice list is paged,** 25 per page, and the filters carry over between pages

## [0.26.0] - 2026-10-08

### Features
- **Time and money on the project Overview.** A new card shows:
  - Hours logged, split into billable and not
  - Hours logged on tasks that have an estimate against the total estimate, in red when over
  - The billable amount: billable hours at the hourly rate, or the fixed price
  - What has been invoiced for the project so far, from lines on sent invoices that are not cancelled, before tax
  - Hours need the tasks module and follow the time page: people without "see all tasks" see only their own time, marked "your time only"
  - Money needs the invoices module. The billable amount of an hourly project is shown only to people who see everyone's time

## [0.25.0] - 2026-10-08

### Features
- **Client Overview tab.** A client page now opens on an Overview with:
  - What the client still owes, per currency, and how many drafts are not sent yet
  - Overdue invoices, with their total and a list linking to each one
  - Open projects with their deadlines (red when late) and task counts
  - Hours logged this month and how many of them are billable. People who see only their own time get "Your hours this month"
  - The contacts, the recently updated tasks and when the client last had activity
  - Money needs the invoices module and hours and tasks need the tasks module; a section the person cannot see is left out
- **Search on the client list.** Searching by name, or by a contact's name or email, filters the list as you type. It works with the archived toggle too, and the archived count follows the search

### Changes
- The profile (contacts, company details, billing, notes) moved to its own Profile tab at `/clients/<id>/profile/`

## [0.24.0] - 2026-10-08

### Features
- **Contacts per client.** The client profile has a Contacts card listing the people at the client, each with a name, role, email and phone. Anyone who can edit clients adds, edits and removes them in a drawer. One contact can be marked Primary and one Billing; marking another moves the mark. The first contact added starts as Primary
- The billing contact's email is used on new invoices when the client has no billing email of its own, before falling back to the client email
- The search palette finds a client by a contact's name or email

### Changes
- The client's own email, phone and address now sit under "Company details" on the profile

### Migrations
- `clients.0006` adds the client contacts table. Existing clients start with no contacts; their email and phone stay as company details

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
