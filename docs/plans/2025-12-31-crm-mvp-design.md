# WebFTL CRM - MVP Design

## Overview

A CRM for small agencies (2-10 people) combining Perfex-style client management with Linear-style project tracking and GitHub integration.

**Target User**: Small software development agency managing clients, projects, and tasks with GitHub-based workflows.

## Tech Stack

- Python 3.12 (local venv)
- Django 5.1
- django-allauth (email/password authentication)
- HTMX 2.0
- Alpine.js 3.x
- Tailwind CSS (CDN)
- PostgreSQL 16 (Docker container)

## Core Data Model

```
Organization (your agency)
├── Users (team members)
│   ├── email, name, role (admin/member)
│   └── GitHub token (for API access)
│
├── Clients
│   ├── name, email, phone, address
│   └── notes
│
└── Projects
    ├── belongs to Client
    ├── name, description
    ├── GitHub repo URL (optional)
    ├── Statuses (ordered, customizable)
    │   └── defaults: Backlog → To Do → In Progress → Review → Done
    │
    └── Tasks
        ├── title, description, status, assignee
        ├── priority (low/medium/high/urgent)
        ├── due_date, time_estimate
        ├── labels (many-to-many)
        ├── github_issue_id (for sync)
        ├── Subtasks (checklist items)
        ├── Comments
        └── Attachments
```

Single-tenant design (one organization per deployment).

## Views & Navigation

### Main Navigation (sidebar)

| Route | Description |
|-------|-------------|
| Dashboard | Overview stats, recent activity |
| Clients | List/grid of clients |
| Projects | All projects (filterable by client) |
| My Tasks | Personal task view across all projects |
| Team | Team members (admin only for management) |
| Settings | Profile, GitHub connection, organization |

### Project Detail Page

- Header: Project name, client, GitHub repo link
- Kanban board with draggable columns
- Toggle between Board view and List view
- Filter bar: assignee, priority, labels, due date

### Task Detail (slide-over panel)

- Opens from Kanban card click
- All task fields editable inline
- Subtasks as checkable list
- Comments thread below
- GitHub section: linked issue, recent commits/PRs

### HTMX-Powered Interactions

- Drag-drop updates status via HTMX (no full page reload)
- Task panel loads via HTMX into slide-over
- Inline editing with HTMX PATCH requests
- Alpine.js for local UI state (dropdowns, modals)

## Authentication & Permissions

### Authentication

- django-allauth with email/password
- No social auth for MVP

### Roles

| Role | Permissions |
|------|-------------|
| Admin | Full access to all features |
| Member | Cannot delete clients/projects, cannot see billing settings |

## GitHub Integration

### Connection Setup

- User connects GitHub account via OAuth (stored per user)
- Project links to a GitHub repository URL
- Sync enabled/disabled per project

### Issue Sync (bidirectional)

- **GitHub → CRM**: Webhook receives issue events, creates/updates tasks
- **CRM → GitHub**: Creating a task can optionally create a GitHub issue
- Mapping: Issue title ↔ Task title, body ↔ description, labels ↔ labels
- Status sync: Closing issue → moves task to Done (configurable)

### PR/Commit Tracking

- Webhook listens for push and pull_request events
- Match commits/PRs to tasks via:
  - Commit message contains `#TASK-123` or task ID
  - PR references task in description
- Task detail shows linked commits and PR status (open/merged/closed)

### Implementation

- Use GitHub App or OAuth App
- Webhooks for real-time sync
- Store `github_issue_id` and `github_issue_number` on tasks
- Background job (Django-Q or Celery) for sync reliability

## Project Structure

```
webftl_crm/
├── docker-compose.yml      # PostgreSQL only
├── requirements.txt
├── manage.py
├── config/                 # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── accounts/           # User auth, profiles, team
│   ├── clients/            # Client management
│   ├── projects/           # Projects, statuses
│   ├── tasks/              # Tasks, subtasks, comments, attachments
│   └── integrations/       # GitHub sync, webhooks
├── templates/
│   ├── base.html           # Layout with nav, HTMX/Alpine includes
│   ├── components/         # Reusable partials (cards, modals, forms)
│   └── <app>/              # App-specific templates
└── static/
    └── css/                # Custom styles if needed
```

## Key Dependencies

| Package | Purpose |
|---------|---------|
| django-allauth | Authentication |
| django-htmx | HTMX request helpers |
| PyGithub or httpx | GitHub API |
| Pillow | Image attachments |
| whitenoise | Static files in production |
| psycopg | PostgreSQL adapter |

## MVP Scope

### In Scope

| Feature | Details |
|---------|---------|
| Auth | Email/password via allauth, Admin/Member roles |
| Clients | CRUD, basic info (name, email, phone, address, notes) |
| Projects | CRUD, linked to client, customizable statuses |
| Kanban Board | Drag-drop tasks, per-project columns |
| Tasks | Full details: assignee, priority, labels, due date, estimates |
| Subtasks | Checklist items within tasks |
| Comments | Threaded comments on tasks |
| Attachments | File uploads on tasks |
| Views | Project board, My Tasks, filtered views |
| GitHub Sync | Issue bidirectional sync, PR/commit tracking |
| Team | List members, assign to tasks |

### Out of Scope (post-MVP)

- Invoicing, estimates, payments
- Time tracking
- Support tickets
- Client portal
- Notifications (email/in-app)
- Contracts, proposals, documents
- Custom fields
- Reporting/analytics
- Cycles/sprints

## Default Task Statuses

Projects have customizable statuses with these defaults:

1. Backlog
2. To Do
3. In Progress
4. Review
5. Done

## Task Priority Levels

- Low
- Medium
- High
- Urgent
