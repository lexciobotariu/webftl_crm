# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| main    | yes       |

## Reporting a Vulnerability

If you discover a security vulnerability in WebFTL CRM, please report it responsibly.

**Do not** open a public GitHub issue for security bugs.

Instead, email the maintainer with:

- A description of the issue and its impact
- Steps to reproduce
- Any proof-of-concept or suggested fix (if available)

We aim to acknowledge reports within 48 hours and will work with you on a fix and disclosure timeline.

## Security Practices

- Set strong, unique `SECRET_KEY` and `FERNET_KEY` in production (`DEBUG=False`).
- Configure `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and `GITHUB_WEBHOOK_SECRET`.
- Self-registration is disabled; create users through the admin team UI.
- Run `python manage.py check --deploy` before deploying.

See `docs/security/SECURITY_ISSUES.md` for the internal audit history and remaining low-priority items.
