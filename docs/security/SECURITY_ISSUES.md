# Security Audit — WebFTL CRM

**Last updated:** 2026-08-31

This document tracks the security audit findings and their resolution status. It is intended for maintainers, not as a live vulnerability disclosure (see `SECURITY.md` for reporting).

## Summary

| Priority | Open | Fixed |
|----------|------|-------|
| Critical | 0 | 4 |
| High | 0 | 3+ |
| Medium | 0 | 6+ |
| Low | 1 | — |

All critical, high, and medium issues identified in the January 2026 audit have been addressed. One low-priority item remains open.

## Fixed (highlights)

- **Open self-registration** — `NoSignupAccountAdapter` disables public signup; users are created by admins.
- **Weak production settings** — `SECRET_KEY` / `FERNET_KEY` required when `DEBUG=False`; env-driven `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SECURE_*` cookie/HSTS flags, `STORAGES` for WhiteNoise.
- **RBAC gaps** — `access_dashboard`, `access_projects`, `access_tasks`, `access_todos`, and `access_notes` enforced in views (not only the sidebar).
- **GitHub sync authorization** — manual sync requires project manager access; sync uses synchronous httpx with timeout.
- **Webhook bypass** — unsigned payloads rejected when webhook secret is unset (no `DEBUG` bypass).
- **GitHub token encryption** — `EncryptedCharField` on `User.github_token`.
- **File upload validation** — attachment uploads validated in task views.
- **Project/task authorization** — `can_access_project` checks on mutating endpoints.
- **Data model integrity** — `Note.modified_by` uses `SET_NULL`; `Task.status` uses `RESTRICT` (blocks orphaning a status, but still allows the project/client cascade); `EmployeeSalary.user` uses `PROTECT`; user delete blocked when salary records exist.

Per-app audit notes live in this directory (`accounts-audit.md`, `clients-audit.md`, etc.).

## Open — Low Priority

### 1. No rate limiting on account views

**Location:** `apps/accounts/views.py` (team management, preset CRUD)

**Impact:** Brute-force or abuse of authenticated admin endpoints.

**Mitigation:** Deploy behind a reverse proxy with rate limiting, or add Django rate-limit middleware in a future release.

## Verification

```bash
python manage.py check --deploy   # with production env vars set
pytest -m security
```

## Historical detail

Detailed line-by-line findings from the original audit (including items already fixed) were removed from this file to avoid contradictory “fix before production” instructions alongside resolved status markers. Refer to git history before 2026-08-31 for the original narrative.
