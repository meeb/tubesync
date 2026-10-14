---
appliesTo:
- type: capability
  id: run-task
- type: capability
  id: browse-completed-tasks
references:
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#cleanup_completed_tasks
---

# Completed task records are kept for a limited number of days

Records of completed tasks older than the retention period, seven days by default, are deleted when indexing starts.
