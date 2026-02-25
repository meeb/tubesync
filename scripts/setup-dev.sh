#!/usr/bin/env bash
set -euo pipefail

# TubeSync development environment setup script
# Usage: ./scripts/setup-dev.sh

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"

echo "==> Setting up TubeSync dev environment"
echo "    Python: $($PYTHON --version)"
echo "    Repo:   $REPO_ROOT"
echo

# 1. Create a virtualenv if not already in one
if [ -z "${VIRTUAL_ENV:-}" ]; then
    echo "==> Creating virtualenv in .venv/"
    $PYTHON -m venv "$REPO_ROOT/.venv"
    source "$REPO_ROOT/.venv/bin/activate"
    echo "    Activated .venv"
else
    echo "==> Using existing virtualenv: $VIRTUAL_ENV"
fi

# 2. Install dependencies
echo "==> Installing dependencies from requirements.txt"
pip install --upgrade pip -q
pip install -r "$REPO_ROOT/requirements.txt" -q
pip install -r "$REPO_ROOT/requirements-dev.txt" -q
echo "    Done"

# 3. Apply yt-dlp patches
echo "==> Applying yt-dlp patches"
SITE_PACKAGES="$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
cp -a "$REPO_ROOT/patches/yt_dlp/"* "$SITE_PACKAGES/yt_dlp/"
echo "    Patched yt_dlp in $SITE_PACKAGES"

# 4. Copy local settings if missing
if [ ! -f "$REPO_ROOT/tubesync/tubesync/local_settings.py" ]; then
    echo "==> Copying local_settings.py.example"
    cp "$REPO_ROOT/tubesync/tubesync/local_settings.py.example" \
       "$REPO_ROOT/tubesync/tubesync/local_settings.py"
else
    echo "==> local_settings.py already exists, skipping"
fi

# 5. Run migrations
echo "==> Running database migrations"
$PYTHON "$REPO_ROOT/tubesync/manage.py" migrate --run-syncdb -v 0

# 6. Collect static files
echo "==> Collecting static files"
$PYTHON "$REPO_ROOT/tubesync/manage.py" collectstatic --noinput -v 0

echo
echo "==> Setup complete!"
echo "    Activate the virtualenv:  source .venv/bin/activate"
echo "    Run the dev server:       cd tubesync && python manage.py runserver"
echo "    Run tests:                cd tubesync && python manage.py test --verbosity=2"
