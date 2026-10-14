---
availability:
- {place: web}
domain: tasks
references:
- kind: code
  role: implementation
  target: tubesync/common/models/tasks.py#TaskHistory
- kind: code
  role: implementation
  target: tubesync/common/huey.py#DjangoBackgroundTasksBackoff
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#cleanup_completed_tasks
- kind: doc
  role: intent
  target: README.md
---

# Run task

TubeSync runs each scheduled task when its time has come and a worker of its queue is free, highest priority first, retrying failures with growing delays and keeping a short record of completed tasks.
