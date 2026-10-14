---
scope: The TubeSync application under tubesync/, its settings and the web templates.
method: Static inspection of source, templates, settings and the README at 9fdbfcba; nothing executed.
covered:
- description: Source, media, metadata and media server models with their signal handlers.
  paths:
  - tubesync/sync/models/
  - tubesync/sync/signals.py
  - tubesync/sync/fields.py
- description: Background tasks, filtering, format matching and the YouTube and media server clients.
  paths:
  - tubesync/sync/tasks.py
  - tubesync/sync/filtering.py
  - tubesync/sync/matching.py
  - tubesync/sync/youtube.py
  - tubesync/sync/mediaservers.py
  - tubesync/sync/hooks.py
  - tubesync/sync/utils.py
  - tubesync/sync/choices.py
- description: Web views, forms, URL routes and page templates.
  paths:
  - tubesync/sync/views/
  - tubesync/sync/forms.py
  - tubesync/sync/urls.py
  - tubesync/sync/templates/
  - tubesync/sync/templatetags/
  - tubesync/tubesync/urls.py
  - tubesync/common/urls.py
  - tubesync/common/templates/
  - tubesync/common/context_processors.py
- description: Task history, task queues and their back-off.
  paths:
  - tubesync/common/models/
  - tubesync/common/huey.py
- description: Settings, container settings and the optional HTTP authentication middleware.
  paths:
  - tubesync/tubesync/settings.py
  - tubesync/tubesync/local_settings.py.container
  - tubesync/common/middleware.py
exclusions:
- description: Container build, service supervision definitions, CI workflows and vendored patches.
  paths:
  - Dockerfile
  - Makefile
  - config/
  - .github/
  - patches/
  - fontawesome-free/
  - tubesync/install_bun.sh
  - tubesync/install_deno.sh
  - tubesync/install_tailwindcss.sh
  - tubesync/download_asfald.func.inc.sh
  - tubesync/download_gh_release.func.inc.sh
  - tubesync/upgrade_yt-dlp.sh
  - tubesync/restart_services.sh
  - tubesync/verify_bun.ts
  - tubesync/shasum.py
- description: Tests, test data and test helpers.
  paths:
  - tubesync/sync/tests/
  - tubesync/sync/testdata/
  - tubesync/common/tests.py
  - tubesync/common/testutils.py
  - tubesync/shasum_tests.py
- description: Database migrations.
  paths:
  - tubesync/sync/migrations/
  - tubesync/common/migrations/
- description: Static styles, scripts and images.
  paths:
  - tubesync/common/static/
- description: YouTube extractor plugins and the proof-of-origin token provider used by the downloader.
  paths:
  - tubesync/yt_dlp_plugins/
  - tubesync/bgutil-ytdlp-pot-provider/
  - tubesync/common/yt_dlp.py
unmapped:
- description: Operator management commands run inside the container.
  paths:
  - tubesync/sync/management/
  - tubesync/common/management/
- description: The built-in admin site and its bulk media actions.
  paths:
  - tubesync/sync/admin.py
  - tubesync/common/admin.py
- description: The container health check endpoint and script.
  paths:
  - tubesync/common/views.py
  - tubesync/healthcheck.py
- description: Log capture behind the Logs page.
  paths:
  - tubesync/common/logs/
  - tubesync/common/logger.py
  - tubesync/common/hat_busybox.py
  - tubesync/hat-syslog_tool.py
- description: The overridable custom media filter.
  paths:
  - tubesync/sync/overrides/
limitations: []
---

# Coverage
