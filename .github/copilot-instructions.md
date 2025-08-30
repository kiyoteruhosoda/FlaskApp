# Copilot Instructions for PhotoNest (FlaskApp)
回答は日本語で
コンソール実行時は仮想環境venvを使うため最初に`source /home/kyon/myproject/.venv/bin/activate`を実行
Python実行時は `source /home/kyon/myproject/.venv/bin/activate && python main.py`
開発はDDDベースで層を区切って
同じ処理は共通化して
テストファイルはテストディレクトリに配置すること



## Project Overview
- **PhotoNest** is a family photo viewer and sync platform, with a Python backend (Flask), MariaDB, and Celery-based background processing.
- The system is split into:
  - `webapp/`: Flask app (API, UI, auth, admin, feature modules)
  - `core/`: Core logic (crypto, DB, models, tasks)
  - `cli/`: Celery configuration and task definitions
  - `domain/`: Domain layer (DDD architecture)
  - `application/`: Application services (DDD architecture)
  - `infrastructure/`: Infrastructure layer (DDD architecture)
  - `migrations/`: Alembic DB migrations
  - `tests/`: Pytest-based tests

## Key Workflows
- **Web server**: `python main.py` (uses `.env` for config, run in `.venv` environment)
- **Celery workers**: `celery -A cli.src.celery.tasks worker --loglevel=info` (run in `.venv`)
- **Celery scheduler**: `celery -A cli.src.celery.tasks beat --loglevel=info` (run in `.venv`)
- **DB migration**: `flask db migrate` / `flask db upgrade` (see `README.md`)
- **Environment setup**: Copy `.env.example` to `.env`, install `python-dotenv`, activate `.venv`
- **Google OAuth**: Tokens are AES-256-GCM encrypted; see `README.md` and `core/crypto.py`

## Architecture & Patterns
- **DDD Architecture**: Domain-Driven Design with clear separation of concerns
  - `domain/`: Pure business logic and domain models
  - `application/`: Application services and use cases
  - `infrastructure/`: Data access and external service integration
- **API**: RESTful endpoints under `/api/` (see requirements.md for endpoint/param conventions)
- **DB**: MariaDB 10.11, models in `core/models/`, migrations in `migrations/`
- **Background Workers**: Celery-based async processing for media conversion, thumbnail generation, and Google Photos sync
  - Media playback conversion: `transcode_worker()` in `core/tasks/transcode.py`
  - Thumbnail generation: `thumbs_generate()` in `core/tasks/thumbs_generate.py`
  - Photo picker import: `picker_import_item()` in `core/tasks/picker_import.py`
- **Config**: `.env` for secrets, keys, and DB connection; requires `python-dotenv` for loading
- **i18n**: Translations in `webapp/translations/`, compiled with `pybabel compile -d webapp/translations -f`
- **Security**: Google tokens encrypted, role-based permissions (`current_user.can()`), signed download URLs
- **Media Storage**: Structured by date (`YYYY/MM/DD/`) with originals, playback files, and multi-size thumbnails

## Project Conventions
- **Pagination**: `page`, `pageSize`, `cursor` (Base64URL), `order` params; responses include `next_cursor`/`prev_cursor`
- **Error Handling**: API errors return toast messages; retry logic and error pages for fatal errors
- **Testing**: Use `pytest` in `tests/`; CLI and API both have test coverage
- **Component Structure**: Blueprint pattern with url_prefix: `/api`, `/auth`, `/admin`, `/photo-view`, `/feature-x`
- **Naming**: DB, files, and endpoints follow conventions in `requirements.md`
- **Media Processing**: Videos transcoded to H.264/AAC MP4 (1080p, CRF20), thumbnails in 256/1024/2048px
- **Token Security**: Download URLs use HMAC-signed tokens with expiration (`_sign_payload()` in API routes)

## Integration Points
- **Google API**: OAuth flow, token storage, and refresh logic in `core/models/google_account.py` and `core/crypto.py`
- **Media Processing**: Video conversion and thumbnailing via workers in `core/tasks/`
- **Admin/Settings**: Settings and job history require admin permissions; see UI/validation rules in `requirements.md`
- **File Downloads**: Signed URLs via `/api/dl/<token>` with type-specific paths (`thumbs/`, `playback/`)
- **Authorization**: Role-based access with Permission model; use `@require_roles()` decorator and `current_user.can()`

## Examples
- To add a Google account for sync, insert into `google_account` and set up `.env` as described in `README.md`.
- To migrate DB after model changes: `flask db migrate -m "desc" && flask db upgrade`
- Media API endpoints: `/api/media/<id>/thumb-url` (POST with size), `/api/media/<id>/playback-url` (POST)
- Background task functions return `{"ok": bool, ...}` dicts for test/monitoring compatibility

## References
- See `requirements.md` for detailed API, DB, and UI specs
- See `README.md` and `cli/README.md` for setup and workflow details
- See `core/` and `webapp/` for main logic and API/UI code
