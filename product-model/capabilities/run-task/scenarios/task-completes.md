---
kind: primary
routes:
  web: Web
steps:
- text: A scheduled task has reached its time and its queue has a free worker
  kind: condition
  unattended: true
  entities:
  - {entity: task, effect: reads, facts: [Scheduled at, Priority, Queue]}
  contexts:
    web:
      place: web::tasks
- text: The Product starts the task and shows it as running, with progress for downloads and indexing
  kind: product
  entities:
  - {entity: task, effect: changes, from: Scheduled, to: Running, facts: [Started at, Name]}
  contexts:
    web:
      place: web::tasks
- text: The Product finishes the task and records it as completed
  kind: product
  entities:
  - {entity: task, effect: changes, from: Running, to: Completed, facts: [Finished at]}
  contexts:
    web:
      place: web::completed-tasks
---

# A task runs and completes

## Trigger

A scheduled task reaches its time and a worker of its queue is free.

## Outcome

The task has run and appears among completed tasks.
