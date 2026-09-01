# Contributing to WebFTL CRM

Thanks for your interest in contributing.

## Development setup

1. Clone the repository and create a virtual environment (Python 3.12+).
2. Copy `.env.example` to `.env` and adjust values.
3. Start PostgreSQL: `docker compose up -d db`
4. Install dependencies: `pip install -r requirements-dev.txt`
5. Run migrations: `python manage.py migrate`
6. Create a superuser: `python manage.py createsuperuser`
7. Run the dev server: `python manage.py runserver`

## Running tests

```bash
pytest
```

## Code style

We use [Ruff](https://docs.astral.sh/ruff/) for linting, configured in
`pyproject.toml`. CI runs:

```bash
ruff check .
```

`ruff format` is deliberately not enforced — the codebase predates it and
reformatting would bury real changes in noise.

## Screenshots

The README screenshots are generated from fictional demo data, never from a real
database. To regenerate them:

```bash
createdb webftl_demo
export DATABASE_URL=postgres://postgres:postgres@localhost:5433/webftl_demo
python manage.py migrate
python manage.py seed_demo_data
python manage.py runserver 8765 --noreload &

pip install playwright && playwright install chromium
python scripts/take_screenshots.py
```

`seed_demo_data` refuses to run against a database that already has clients
unless you pass `--force`.

## Pull requests

- Keep changes focused — one logical change per PR when possible.
- Include tests for new behavior.
- Ensure `pytest` and `python manage.py check --deploy` pass (with production env vars set for deploy check).

## Security

Please report security issues privately — see [SECURITY.md](SECURITY.md).
