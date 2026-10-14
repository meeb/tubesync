---
availability:
- {place: web}
domain: tasks
references:
- kind: code
  role: implementation
  target: tubesync/sync/views/tasks.py#TaskScheduleView
- kind: code
  role: implementation
  target: tubesync/sync/forms.py#ScheduleTaskForm
- kind: code
  role: implementation
  target: tubesync/sync/templates/sync/task-schedule.html
---

# Schedule task

The User changes when a scheduled or failed task runs: now, or at a chosen later time.
