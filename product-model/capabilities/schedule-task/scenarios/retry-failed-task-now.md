---
kind: alternative
routes:
  web: Web
steps:
- text: The User chooses the retry control on a task with an error
  kind: actor
  actor: user
  entities:
  - {entity: task, effect: reads, facts: [Name, Last error]}
  contexts:
    web:
      place: web::tasks
- text: The User chooses Schedule task
  kind: actor
  actor: user
  entities:
  - {entity: task, effect: reads, facts: [Scheduled at]}
  contexts:
    web:
      place: web::tasks
- text: The Product schedules the task to run again then
  kind: product
  actor: user
  entities:
  - {entity: task, effect: changes, from: Failed, to: Scheduled, facts: [Scheduled at]}
  contexts:
    web:
      place: web::tasks
---

# Retry a failed task now

## Trigger

A task failed and the User does not want to wait for its retry.

## Outcome

The task is scheduled to run again at the chosen time.
