---
entities:
- entity: task
  shows:
  - Name
  - Queue
  - Started at
  - Finished at
  - Last error
- entity: source
  shows:
  - Name
entryPoints:
- web: /tasks-completed
---

# Completed tasks

The recent record of completed tasks.
