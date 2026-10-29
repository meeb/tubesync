# Development Guide

This guide covers everything you need to set up a local development environment, run
tests, and contribute to TubeSync.

## Prerequisites

- Python 3.10 or later (3.10, 3.11, 3.12, 3.13 are tested in CI)
- [Pipenv](https://pipenv.pypa.io/) for dependency management
- `ffmpeg` installed and available in your `$PATH`
- `mysql_config` or `mariadb_config` if you need the MySQL/MariaDB driver
  (Debian/Ubuntu: `libmysqlclient-dev`)

## Initial setup

1. Clone the repository:

```bash
git clone https://github.com/meeb/tubesync.git
cd tubesync
```

2. Install Python dependencies:

```bash
pipenv install --dev
```

Or, if you prefer using `uv` + `pip` (same as CI):

```bash
python -m pip install uv
pipenv lock
pipenv requirements | tee requirements.txt
uv pip install --system --strict --requirements requirements.txt
```

3. Copy the local settings file:

```bash
cp tubesync/tubesync/local_settings.py.example tubesync/tubesync/local_settings.py
```

This configures a local SQLite database and sensible defaults for development.

4. Run database migrations:

```bash
cd tubesync
python manage.py migrate
```

5. Collect static files:

```bash
python manage.py collectstatic --noinput
```

Or use the Makefile shortcut:

```bash
make build
```

## Running the development server

```bash
make dev
```

This starts Django's built-in `runserver` on `http://localhost:8000`.

You can also run it directly:

```bash
cd tubesync
python manage.py runserver
```

## Running tests

Run the full test suite:

```bash
make test
```

Or directly with Django:

```bash
cd tubesync
python manage.py test --verbosity=2
```

For more verbose output with debug logging:

```bash
cd tubesync
TUBESYNC_DEBUG=True python manage.py test --no-input --buffer --verbosity=2
```

The CI runs the test suite against Python 3.10, 3.11, 3.12, and 3.13. Make sure your
changes pass on at least Python 3.10 before submitting a PR.

## Linting

The CI uses [ruff](https://github.com/astral-sh/ruff) for linting. Run it locally:

```bash
cd tubesync
uvx ruff check --target-version py310
```

Current ignored rules: `E701`, `E722`, `E731`.

## Project structure

```
tubesync/
├── tubesync/              # Django project root
│   ├── tubesync/          # Django project config (settings, urls, wsgi)
│   ├── common/            # Shared app (base templates, utils, middleware, task queue)
│   └── sync/              # Main app (sources, media, downloads, media servers)
├── docs/                  # Documentation
│   └── assets/            # Screenshots and images
├── patches/               # Patches applied to yt-dlp
├── config/                # yt-dlp configuration
├── Dockerfile             # Multi-stage container build
├── Makefile               # Dev shortcuts (build, test, dev, container)
├── Pipfile                # Python dependencies
└── dev.env                # Environment variables for local container testing
```

### Key files

| File | Purpose |
|------|---------|
| `sync/models/` | Source, Media, Metadata, MediaServer models |
| `sync/views.py` | All web interface views |
| `sync/tasks.py` | Huey background tasks (indexing, downloading) |
| `sync/signals.py` | Django signals for task triggers |
| `sync/youtube.py` | yt-dlp integration layer |
| `sync/matching.py` | Media format selection logic |
| `sync/choices.py` | Enum choices (schedules, resolutions, codecs) |
| `common/huey.py` | Custom Huey task queue with SQLite storage |
| `common/utils.py` | Shared utilities (env parsing, file ops) |

## Creating a superuser

To access the Django admin at `/admin`:

```bash
cd tubesync
python manage.py createsuperuser
```

## Running with Docker locally

Build and run the container:

```bash
make container
make runcontainer
```

This uses `dev.env` for environment variables and exposes the app on port `4848`.

## Management commands

TubeSync ships several management commands for common operations:

| Command | Purpose |
|---------|---------|
| `import-existing-media` | Import already-downloaded media files |
| `list-sources` | List all configured sources |
| `delete-source` | Delete a source and its media |
| `reset-tasks` | Reset stuck or failed tasks |
| `reset-metadata` | Reset cached metadata |
| `sync-missing-metadata` | Re-fetch missing metadata |
| `create-tvshow-nfo` | Generate NFO files for media |
| `youtube-add-subscriptions` | Bulk-add YouTube subscriptions |

Run any command with:

```bash
cd tubesync
python manage.py <command-name> --help
```

## Submitting a pull request

1. Create a feature branch from `main`
2. Make your changes
3. Run `make test` and ensure all tests pass
4. Run `uvx ruff check --target-version py310` in `tubesync/` and fix any issues
5. Open a PR against `main`

The CI will automatically run the test suite and a container build/analysis.
