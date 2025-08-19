# Copilot Instructions for PhotoNest (FlaskApp)
回答は日本語で

## Project Overview
- **PhotoNest** is a family photo viewer and sync platform, with a Python backend (Flask/FastAPI style), MariaDB, and a CLI utility (`fpv`).
- The system is split into:
  - `webapp/`: Flask app (API, UI, auth, admin, feature modules)
  - `core/`: Core logic (crypto, DB, models, tasks)
  - `cli/`: CLI utilities for sync, config, and Google API integration
  - `migrations/`: Alembic DB migrations
  - `tests/`: Pytest-based tests

## Key Workflows
- **Web server**: `python main.py` (uses `.env` for config)
- **DB migration**: `flask db migrate` / `flask db upgrade` (see `README.md`)
- **CLI install**: `cd cli && python -m pip install -e .`
- **CLI usage**: `fpv config check`, `fpv sync --dry-run`, `fpv sync --no-dry-run`
- **Google OAuth**: Tokens are AES-256-GCM encrypted; see `README.md` and `core/crypto.py`

## Architecture & Patterns
- **API**: RESTful endpoints under `/api/` (see requirements.md for endpoint/param conventions)
- **DB**: MariaDB 10.11, models in `core/models/`, migrations in `migrations/`
- **Batch/Worker**: Cron-based sync, video conversion, and thumbnail generation (see `core/tasks/`)
- **Config**: `.env` for secrets, keys, and DB connection; see sample in `README.md`
- **i18n**: Translations in `webapp/translations/`, compiled with `pybabel compile -d webapp/translations -f`
- **Security**: Google tokens encrypted, admin actions require explicit permissions

## Project Conventions
- **Pagination**: `page`, `pageSize`, `cursor` (Base64URL), `order` params; responses include `next_cursor`/`prev_cursor`
- **Error Handling**: API errors return toast messages; retry logic and error pages for fatal errors
- **Testing**: Use `pytest` in `tests/`; CLI and API both have test coverage
- **Component Structure**: UI routes and API endpoints are mapped in `requirements.md` and `webapp/`
- **Naming**: DB, files, and endpoints follow conventions in `requirements.md`

## Integration Points
- **Google API**: OAuth flow, token storage, and refresh logic in `core/models/google_account.py` and `core/crypto.py`
- **Media Processing**: Video conversion and thumbnailing via workers in `core/tasks/`
- **Admin/Settings**: Settings and job history require admin permissions; see UI/validation rules in `requirements.md`

## Examples
- To add a Google account for sync, insert into `google_account` and set up `.env` as described in `cli/README.md`.
- To run a dry-run sync: `fpv sync --dry-run`
- To migrate DB after model changes: `flask db migrate -m "desc" && flask db upgrade`

## References
- See `requirements.md` for detailed API, DB, and UI specs
- See `README.md` and `cli/README.md` for setup and workflow details
- See `core/` and `webapp/` for main logic and API/UI code
