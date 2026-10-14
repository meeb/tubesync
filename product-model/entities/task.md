---
domain: tasks
references:
- kind: code
  role: implementation
  target: tubesync/common/models/tasks.py#TaskHistory
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py
---

# Task

A piece of background work TubeSync schedules and runs: indexing a Source, fetching metadata, downloading media or thumbnails, checking or renaming media, deleting a Source or refreshing a media server.

## Information kept

- **Name** — what the task does and for which Source or media item, with its progress or status while running
- **Priority** — its priority in its queue
- **Queue** — the queue it runs in: database, filesystem, networking or limited networking
- **Scheduled at** — when it is due to run
- **Attempts** — how many times it has run
- **Last error** — the error of its last failed run
- **Started at** — when its last run started
- **Finished at** — when its last run ended

## States

### Scheduled

Waiting for its time or for a free worker.

### Running

Being worked on now.

### Failed

Its last run hit an error; it is retried while attempts remain.

### Completed

Finished; its record is kept for a few days.

### Revoked

Cancelled by the User; it will not run.
