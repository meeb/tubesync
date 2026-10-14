---
availability:
- {place: web}
domain: tasks
references:
- kind: code
  role: implementation
  target: tubesync/sync/views/tasks.py#CompletedTasksView
- kind: code
  role: implementation
  target: tubesync/sync/templates/sync/tasks-completed.html
---

# Browse completed tasks

The User reads the recent record of completed tasks, with errors where a task failed, for all Sources or one.
