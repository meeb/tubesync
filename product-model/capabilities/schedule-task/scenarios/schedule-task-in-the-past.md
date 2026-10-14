---
kind: validation
routes:
  web: Web
steps:
- text: The User chooses a time before now and submits
  kind: actor
  actor: user
  entities:
  - {entity: task, effect: reads, facts: [Scheduled at]}
  contexts:
    web:
      place: web::tasks
- text: The Product refuses with "The date and time must be in the future."
  kind: product
  actor: user
  entities:
  - {entity: task, effect: reads, facts: []}
  contexts:
    web:
      place: web::tasks
---

# Refuse a time in the past

## Trigger

The User picks a time before now.

## Outcome

The task keeps its schedule and the form says the time must be in the future.
