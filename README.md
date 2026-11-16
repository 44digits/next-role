# Next Role

A private, single-user job application tracker for opportunities, company contacts,
application stages, related documents, and follow-up reporting.

## Features

- Drag-and-drop kanban board grouping jobs by their current stage, with an
  auditable status history and a combined activity feed.
- Company records and links, jobs with posting and related links, and contacts
  associated with companies and optionally with multiple jobs.
- A filterable contact directory and global quick logger for outbound/inbound
  email, LinkedIn messages, phone calls, interviews, and other interactions.
- Follow-up tasks associated with a contact, a job, or both, with due dates,
  completion tracking, and overdue/upcoming task views.
- Multi-file PDF uploads attached to jobs (job descriptions, resumes, applications,
  cover letters, or other documents), limited to 10 MB per file. Extracted PDF
  text is searchable and documents can be previewed in the browser.
- Reports for applications applied within a date range, grouped by current status,
  pipeline conversion, weekly outbound activity by type, and contacts not
  contacted within 30, 60, or 180 days.

## Local development

The project uses `uv` for Python version and dependency management. Install `uv`,
then from the repository root run:

```sh
export DJANGO_DEBUG=true
export DJANGO_SECRET_KEY='local-only-development-secret'
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

Open <http://127.0.0.1:8000/> and sign in with the superuser account. By default,
local development uses SQLite and stores uploaded files in `media/`.

Run the test suite and lint checks with:

```sh
uv run python manage.py test
uv run ruff check .
uv run ruff format --check .
```

To select another Python release, update `.python-version` with `uv python pin
<version>` and sync the environment with `uv sync`.

## Containerized development

Copy `.env.example` to `.env`, change the local credentials, and start the
application and PostgreSQL:

```sh
docker compose up --build
```

The application is available at <http://127.0.0.1:8000/>. Create the first login
account in another terminal:

```sh
docker compose exec web /opt/venv/bin/python manage.py createsuperuser
```

PostgreSQL data and uploaded PDFs are stored in named Docker volumes. Back up
both volumes; job records and uploaded documents are not disposable application
cache.

## Configuration

Important settings are provided through environment variables:

- `DJANGO_SECRET_KEY`: required when `DJANGO_DEBUG` is false. Use a unique
  random secret in deployed environments.
- `DJANGO_DEBUG`: enable only for local development.
- `DJANGO_ALLOWED_HOSTS`: comma-separated allowed host names.
- `DJANGO_CSRF_TRUSTED_ORIGINS`: comma-separated trusted origins for HTTPS
  deployments.
- `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_PORT`: configure PostgreSQL.
  If `DB_HOST` is unset, SQLite is used.
- `DJANGO_MEDIA_ROOT`: location for local uploaded PDFs.
- `DJANGO_FILE_STORAGE_BACKEND`: Django storage backend dotted path; defaults
  to local file storage and can be changed for a cloud object-storage backend.
- `DJANGO_STATICFILES_STORAGE_BACKEND`: optional static-file storage backend;
  production defaults to WhiteNoise's compressed manifest storage.

For a cloud deployment, configure a strong secret key, disable debug mode, set
allowed hosts and trusted HTTPS origins, and use managed PostgreSQL and durable
file storage. The Docker image serves Django through Gunicorn; put it behind an
HTTPS-capable reverse proxy or cloud ingress.

## Access and data model

There is no public registration flow. Create the initial user with Django's
`createsuperuser` command. All tracker pages require authentication.

Each job belongs to a company and may have zero or more contacts from that
company. A contact may be related to multiple jobs. Status transitions are
preserved in history. Interactions belong to a contact and can optionally be
linked to a job, provided that contact is associated with that job. Tasks may
link to a contact, a job, or both. Each contact's last-contacted date is
maintained from its interaction history. Uploaded PDFs and extracted text are
stored separately so a future object-storage backend can replace local files.
