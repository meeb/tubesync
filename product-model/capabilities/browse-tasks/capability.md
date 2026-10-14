---
availability:
- {place: web}
domain: tasks
references:
- kind: code
  role: implementation
  target: tubesync/sync/views/tasks.py#TasksView
- kind: code
  role: implementation
  target: tubesync/sync/templates/sync/tasks.html
---

# Browse tasks

The User sees what TubeSync is doing: running tasks, tasks with errors and when they will be retried, and tasks scheduled to run, each linked to its Source or media item.
