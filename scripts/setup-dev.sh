#!/usr/bin/env bash
set -euo pipefail

# TubeSync development environment setup script
# Usage: ./scripts/setup-dev.sh

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"

# Fail fast if Python is too old (Django 6 requires 3.12+)
"${PYTHON}" -c 'import sys; v=sys.version_info; (v.major==3 and v.minor>=12) or (print(f"Error: Python 3.12+ required for Django 6. Found {v.major}.{v.minor}", file=sys.stderr), sys.exit(1))' || exit 1

echo "==> Setting up TubeSync dev environment"
echo "    Python: $($PYTHON --version)"
echo "    Repo:   $REPO_ROOT"
echo

# 1. Ensure uv is available
if ! command -v uv >/dev/null 2>&1; then
    echo "==> Installing uv"
    "${PYTHON}" -m pip install uv -q
fi

# 2. Create a virtualenv if not already in one
if [ -z "${VIRTUAL_ENV:-}" ]; then
    echo "==> Creating virtualenv in .venv/"
    uv venv "$REPO_ROOT/.venv" --python "${PYTHON}"
    source "$REPO_ROOT/.venv/bin/activate"
    echo "    Activated .venv"
else
    echo "==> Using existing virtualenv: $VIRTUAL_ENV"
fi

# 3. Install dependencies from Pipfile (via uv)
echo "==> Installing dependencies from Pipfile"
uv --no-config --no-managed-python --no-progress tool run pipenv requirements --no-lock --dev \
    | uv pip install -q -r -
echo "    Done"

# 4. Apply yt-dlp patches
echo "==> Applying yt-dlp patches"
SITE_PACKAGES="$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
cp -a "$REPO_ROOT/patches/yt_dlp/"* "$SITE_PACKAGES/yt_dlp/"
echo "    Patched yt_dlp in $SITE_PACKAGES"

# 5. Copy local settings if missing
if [ ! -f "$REPO_ROOT/tubesync/tubesync/local_settings.py" ]; then
    echo "==> Copying local_settings.py.example"
    cp "$REPO_ROOT/tubesync/tubesync/local_settings.py.example" \
       "$REPO_ROOT/tubesync/tubesync/local_settings.py"
else
    echo "==> local_settings.py already exists, skipping"
fi

# 6. Download Tailwind CSS CLI if not present (verified via asfald)
if [ ! -x "$REPO_ROOT/tailwindcss" ]; then
    echo "==> Downloading Tailwind CSS CLI (with asfald checksum verification)"
    bash "${REPO_ROOT}/tubesync/install_tailwindcss.sh" "${REPO_ROOT}"
else
    echo "==> Tailwind CSS CLI already present"
fi

# 7. Compile Tailwind CSS
echo "==> Compiling Tailwind CSS"
# Maybe use `make css` here instead?
"$REPO_ROOT/tailwindcss" --input "$REPO_ROOT/tubesync/common/static/styles/tailwind/tubesync.css" --output "$REPO_ROOT/tubesync/common/static/styles/tailwind/tubesync-compiled.css" --cwd "$REPO_ROOT"

# 8. Run migrations
echo "==> Running database migrations"
$PYTHON "$REPO_ROOT/tubesync/manage.py" migrate --run-syncdb -v 0

# 9. Collect static files
echo "==> Collecting static files"
$PYTHON "$REPO_ROOT/tubesync/manage.py" collectstatic --noinput -v 0

echo
echo "==> Setup complete!"
echo "    Activate the virtualenv:  source .venv/bin/activate"
echo "    Run the dev server:       cd tubesync && python manage.py runserver"
echo "    Run tests:                cd tubesync && python manage.py test --verbosity=2"
