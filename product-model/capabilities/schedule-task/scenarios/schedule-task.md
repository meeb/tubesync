---
kind: primary
routes:
  web: Web
steps:
- text: The User chooses the play control on a task scheduled for later
  kind: actor
  actor: user
  entities:
  - {entity: task, effect: reads, facts: [Name, Scheduled at]}
  contexts:
    web:
      place: web::tasks
- text: The Product proposes the next minute as the time to run
  kind: product
  actor: user
  entities:
  - {entity: task, effect: reads, facts: [Scheduled at]}
  contexts:
    web:
      place: web::tasks
- text: The User keeps or changes the time and chooses Schedule task
  kind: actor
  actor: user
  entities:
  - {entity: task, effect: reads, facts: [Scheduled at]}
  contexts:
    web:
      place: web::tasks
- text: The Product reschedules the task for that time and shows "Scheduled task"
  kind: product
  actor: user
  entities:
  - {entity: task, effect: changes, facts: [Scheduled at, Name]}
  contexts:
    web:
      place: web::tasks
---

# Run a scheduled task sooner

## Trigger

The User does not want to wait for a task schedule.

## Outcome

The task is requested to run at the chosen time.

## Edge cases

- Running when a queue worker is free is not guaranteed at the exact time chosen.
