---
kind: alternative
routes:
  web: Web
steps:
- text: The User opens the Tasks page filtered to a Source
  kind: actor
  actor: user
  entities:
  - {entity: source, effect: reads, facts: []}
  - {entity: task, effect: reads, facts: []}
  contexts:
    web:
      place: web::tasks
- text: The Product lists only tasks for that Source and names the filter
  kind: product
  actor: user
  entities:
  - {entity: task, effect: reads, facts: [Name, Scheduled at]}
  - {entity: source, effect: reads, facts: [Name]}
  contexts:
    web:
      place: web::tasks
---

# Browse the tasks of one source

## Trigger

The User wants the tasks of one Source.

## Outcome

Only tasks for that Source are listed, with a note naming it.
