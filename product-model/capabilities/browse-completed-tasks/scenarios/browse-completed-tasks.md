---
kind: primary
routes:
  web: Web
steps:
- text: The User opens Completed tasks
  kind: actor
  actor: user
  entities:
  - {entity: task, effect: reads, facts: []}
  contexts:
    web:
      place: web::completed-tasks
- text: The Product lists completed tasks newest first
  kind: product
  actor: user
  entities:
  - {entity: task, effect: reads, facts: [Name, Queue, Started at, Finished at, Last error]}
  contexts:
    web:
      place: web::completed-tasks
- text: The User reads the completed tasks
  kind: actor
  actor: user
  entities:
  - {entity: task, effect: reads, facts: [Name, Finished at, Last error]}
  contexts:
    web:
      place: web::completed-tasks
---

# Browse completed tasks

## Trigger

The User wants to know what TubeSync has done.

## Outcome

The User sees completed tasks newest first, with their queue, times and any error.
