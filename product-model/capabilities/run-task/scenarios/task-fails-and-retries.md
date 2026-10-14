---
kind: edge
routes:
  web: Web
steps:
- text: A running task hits an error
  kind: condition
  unattended: true
  entities:
  - {entity: task, effect: reads, facts: [Name]}
  contexts:
    web:
      place: web::tasks
- text: The Product records the error and the attempt
  kind: product
  entities:
  - {entity: task, effect: changes, from: Running, to: Failed, facts: [Last error, Attempts]}
  contexts:
    web:
      place: web::tasks
- text: The Product schedules the task again after a delay that grows with each attempt, while attempts remain
  kind: product
  entities:
  - {entity: task, effect: changes, from: Failed, to: Scheduled, facts: [Scheduled at]}
  contexts:
    web:
      place: web::tasks
---

# A task fails and is retried

## Trigger

A running task hits an error.

## Outcome

The task shows its error and the time it will be retried.
