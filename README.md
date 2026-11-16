# Next Role

A private, single-user job application tracker for opportunities, company contacts,
application stages, related documents, and follow-up reporting.

## Features

- Kanban board grouping jobs by their current stage, with stage-change history.
- Company records and links, jobs with posting and related links, and contacts
  associated with companies and optionally with multiple jobs.
- Contact interaction history for email, phone calls, interviews, and other events.
- PDF documents attached to each job (resume, application, cover letter, or other),
  limited to 10 MB per file.
- Reports for applications applied within a date range, grouped by current status,
  and contacts without an interaction in the rolling six months.

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
docker compose exec web uv run python manage.py createsuperuser
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
linked to a job.
