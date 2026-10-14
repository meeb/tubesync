---
entities:
- entity: task
  shows:
  - Name
  - Priority
  - Queue
  - Scheduled at
  - Attempts
  - Last error
  - Started at
  collects:
  - Scheduled at
- entity: source
  shows:
  - Name
entryPoints:
- web: /tasks
---

# Tasks

Running, failed and scheduled tasks, with cancelling, rescheduling and resetting.
