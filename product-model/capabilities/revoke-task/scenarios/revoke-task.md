---
kind: primary
routes:
  web: Web
steps:
- text: The User chooses the stop control on a task scheduled for later
  kind: actor
  actor: user
  entities:
  - {entity: task, effect: reads, facts: [Name, Scheduled at]}
  contexts:
    web:
      place: web::tasks
- text: The Product revokes the task and marks it revoked
  kind: product
  actor: user
  entities:
  - {entity: task, effect: changes, from: Scheduled, to: Revoked, facts: [Name]}
  contexts:
    web:
      place: web::tasks
- text: The Product shows "Revoked task" with its id
  kind: product
  actor: user
  entities:
  - {entity: task, effect: reads, facts: []}
  contexts:
    web:
      place: web::tasks
---

# Revoke a scheduled task

## Trigger

The User does not want a scheduled task to run.

## Outcome

The task will not run and is marked revoked.
