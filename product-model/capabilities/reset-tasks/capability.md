---
availability:
- {place: web}
domain: tasks
references:
- kind: code
  role: implementation
  target: tubesync/sync/views/tasks.py#ResetTasks
- kind: code
  role: implementation
  target: tubesync/sync/templates/sync/tasks-reset.html
---

# Reset tasks

The User deletes every current task and has each Source checked again, so that the tasks TubeSync needs are created afresh, for example after files were moved or restored on disk.
