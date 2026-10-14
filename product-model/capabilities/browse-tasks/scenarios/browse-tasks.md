---
kind: primary
routes:
  web: Web
steps:
- text: The User opens the Tasks page
  kind: actor
  actor: user
  entities:
  - {entity: task, effect: reads, facts: []}
  contexts:
    web:
      place: web::tasks
- text: The Product lists running tasks, tasks with errors and scheduled tasks by priority and time
  kind: product
  actor: user
  entities:
  - {entity: task, effect: reads, facts: [Name, Priority, Queue, Scheduled at, Attempts, Last error, Started at]}
  contexts:
    web:
      place: web::tasks
- text: The User reads each task, its error and when it runs next
  kind: actor
  actor: user
  entities:
  - {entity: task, effect: reads, facts: [Name, Last error, Scheduled at]}
  contexts:
    web:
      place: web::tasks
---

# Browse the task queue

## Trigger

The User opens the Tasks page.

## Outcome

The User sees running, failed and scheduled tasks in priority order.
