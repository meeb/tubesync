---
appliesTo:
- type: capability
  id: schedule-task
- type: entity
  id: task
  facts:
  - Scheduled at
references:
- kind: code
  role: implementation
  target: tubesync/sync/views/tasks.py#TaskScheduleView
---

# A task is rescheduled only for now or a later time

Choosing a time before now is refused; the time offered by default is the next minute.
