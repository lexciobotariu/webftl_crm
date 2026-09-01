# WebFTL CRM

A personal CRM built for managing clients, projects, and tasks. I built this for my own freelancing needs — tracking who I'm working with, what's in progress, and what's next. It's lightweight, self-hosted, and gets out of your way.

You're free to use it, modify it, resell it, or do whatever you want with it. See [LICENSE](LICENSE) for details.

![Dashboard](screenshots/dashboard.png)

## Features

- **Clients** — contact info, notes, linked projects and todos
- **Projects** — overview with stats, activity log, GitHub repo sync (experimental)
- **Tasks** — list and kanban board views with drag-and-drop, subtasks, comments, attachments, labels, and activity tracking
- **Todos** — personal to-do list with optional client association and due dates
- **Notes** — quick notes attached to clients
- **Salaries** — employee salary tracking with monthly breakdowns and payment records
- **Team** — user management with role-based access control (RBAC), permission presets, and user deactivation
- **Dashboard** — at-a-glance stats, recent tasks, and pending todos

## Screenshots

<details>
<summary>Client Detail</summary>

![Client Detail](screenshots/client-detail.png)
</details>

<details>
<summary>Project Overview</summary>

![Project Overview](screenshots/project-overview.png)
</details>

<details>
<summary>Task List</summary>

![Task List](screenshots/task-list.png)
</details>

<details>
<summary>Kanban Board</summary>

![Kanban Board](screenshots/kanban-board.png)
</details>

<details>
<summary>Task Detail (Sidebar)</summary>

![Task Detail Sidebar](screenshots/task-detail-sidebar.png)
</details>

<details>
<summary>Task Detail (Full Page)</summary>

![Task Detail Full Page](screenshots/task-detail-fullpage.png)
</details>

## Tech Stack

- **Backend:** Django 5.1, Python 3.12+
- **Frontend:** HTMX, Alpine.js, Tailwind CSS
- **Database:** PostgreSQL 16
- **Auth:** django-allauth (email-based, no username)
- **Icons:** Lucide

## Getting Started

### Prerequisites

- Python 3.12+
- Docker (for the database)

### 1. Clone the repo

```bash
git clone https://github.com/lexciobotariu/webftl_crm.git
cd webftl_crm
```

### 2. Start the database

```bash
docker compose up -d
```

This starts a PostgreSQL 16 container on port 5433.

### 3. Set up the environment

```bash
cp .env.example .env
```

Edit `.env` if needed. The defaults work out of the box for local development.

### 4. Create a virtual environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 5. Run migrations and create a superuser

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 6. Start the dev server

```bash
python manage.py runserver
```

Open [http://localhost:8000](http://localhost:8000) and log in.

## Running Tests

The test tooling lives in `requirements-dev.txt`, which is not installed by the
steps above:

```bash
pip install -r requirements-dev.txt
pytest
```

## Frontend dependencies

There is no build step. HTMX, Alpine.js (plus the `sort` and `collapse` plugins),
Lucide and Iconify are loaded from a CDN, each pinned to an exact version and
verified with Subresource Integrity — bumping one means recomputing its
`integrity` hash in `templates/base.html`.

Tailwind is the exception: it is loaded from `cdn.tailwindcss.com`, which is a
versionless in-browser JIT compiler. That means no pinning, no SRI, a runtime
dependency on the CDN, and a slower first paint than a compiled stylesheet. It is
a deliberate tradeoff to keep the project buildless; replacing it with a compiled
Tailwind build is the first thing to do if you deploy this somewhere that matters.

## GitHub integration

The GitHub sync (repo issues ↔ tasks, plus the webhook) is **experimental**. It
covers issue create/close in one direction and has seen limited real-world use.
Treat it as a starting point rather than a finished feature.

## License

MIT — do whatever you want with it.
