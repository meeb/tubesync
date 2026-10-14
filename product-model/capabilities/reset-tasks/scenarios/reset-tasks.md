---
kind: primary
routes:
  web: Web
steps:
- text: The User chooses Reset tasks and confirms
  kind: actor
  actor: user
  entities:
  - {entity: task, effect: reads, facts: []}
  contexts:
    web:
      place: web::tasks
- text: The Product deletes every current task
  kind: product
  actor: user
  entities:
  - {entity: task, effect: removes, from: Scheduled}
  contexts:
    web:
      place: web::tasks
- text: The Product checks each Source directory and saves each Source again, which re-checks all its media
  kind: product
  actor: user
  entities:
  - {entity: source, effect: reads, facts: [Directory]}
  - {entity: task, effect: creates, to: Scheduled, facts: [Name, Scheduled at]}
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::tasks
- text: The Product shows "All tasks have been reset"
  kind: product
  actor: user
  entities:
  - {entity: task, effect: reads, facts: []}
  contexts:
    web:
      place: web::tasks
---

# Reset all tasks

## Trigger

TubeSync state no longer matches what is on disk.

## Outcome

Every old task is gone and new tasks are created where each Source and media item needs them.
