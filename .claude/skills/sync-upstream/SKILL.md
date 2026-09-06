---
name: sync-upstream
description: Pull the latest changes from meeb/tubesync (upstream) into this fork's main without heavy manual merging. Use when the user asks to sync/update from upstream, "fork master beziehen", "upstream mergen", or pull the newest upstream changes.
---

# Sync upstream (meeb/tubesync) into this fork

This repo is a fork of `meeb/tubesync`. `origin` = masterdot/tubesync, `upstream` = meeb/tubesync.
Local `main` carries custom commits on top of upstream (direct-download API, source bulk-import API,
embedded PostgreSQL backend, SQLite lock-contention fixes).

## Principles

- **Merge, not rebase.** `main` is published to `origin`; rebasing would force-push and re-conflict
  on every custom commit.
- **`git rerere` is enabled** (`git config rerere.enabled true`). Recorded conflict resolutions from
  past syncs replay automatically. First sync recorded: 2026-09-06 (merge `a60dccbc`).
- Conflicts are almost always just **import-line collisions** for the custom `sqlite_retry_delay`
  helper. Resolution is always "keep both sides".

## Procedure

1. Preconditions: clean working tree (`git status`), on `main`, `main` == `origin/main`.
2. Fetch and branch:
   ```
   git fetch upstream
   git config rerere.enabled true          # idempotent, ensure it's on
   git checkout -b sync-upstream-<YYYY-MM-DD>
   git merge upstream/main
   ```
3. Resolve conflicts (rerere may pre-resolve them — check `git rerere status`):
   - `tubesync/common/huey.py`, `tubesync/sync/models/media.py`, `tubesync/sync/tasks.py`:
     import-line collisions → keep **both** the custom import (`sqlite_retry_delay`,
     sometimes an extra call) **and** the upstream import (`retry_django_db`,
     `truncate_filename`, …).
   - `tubesync/sync/tasks.py` `save_model`/`update_model`: keep the custom
     `sqlite_retry_delay()` one-liner **and** upstream's `@retry_django_db(3)` decorator.
   - `Pipfile`: usually take upstream's version of the conflicting line.
   - Anything else: read both sides, prefer keeping custom behavior layered on top of upstream.
4. Watch out for stray untracked files being swept in by `git add -A` (e.g. local docs,
   `*.code-workspace`) — unstage them before committing the merge.
5. Verify:
   - `git rev-list --left-right --count upstream/main...HEAD` → left count must be `0`.
   - Migration chain linear: custom `sync/migrations/00NN_*` must depend on upstream's latest
     `sync/migrations/` head. If upstream added a migration with the same number, renumber the
     custom one and fix its `dependencies`.
   - `python3 -c "import ast; [ast.parse(open(f).read(), f) for f in [...conflicted .py files...]]"`
   - Confirm imported symbols exist (`grep -n "def retry_django_db" tubesync/common/yt_dlp.py`, etc).
   - There is **no local Python env** — real tests only run in Docker or the fork's
     `test-build.yaml` workflow (workflow_dispatch). Tell the user to run CI before shipping an image.
6. Land it:
   ```
   git checkout main
   git merge --ff-only sync-upstream-<YYYY-MM-DD>
   git push origin main
   git branch -d sync-upstream-<YYYY-MM-DD>
   ```
7. Update the memory file `upstream-sync-workflow.md` with the new merge commit hash and any new
   conflict patterns or dropped patches.

## History

- **2026-09-06** (merge `a60dccbc`): 72 upstream commits. Conflicts in Pipfile, huey.py, media.py,
  tasks.py — all trivial. Dropped `patches/hat/juggler/server.py` (Python 3.13 hat-juggler
  NameError workaround); upstream `b02246e2` supersedes it with `hat-juggler = "!=0.7.4"`.
