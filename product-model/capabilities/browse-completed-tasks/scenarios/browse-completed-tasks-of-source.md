---
kind: alternative
routes:
  web: Web
steps:
- text: The User chooses View tasks linked to this source
  kind: actor
  actor: user
  entities:
  - {entity: source, effect: reads, facts: [Name]}
  - {entity: task, effect: reads, facts: []}
  contexts:
    web:
      place: web::source
- text: The Product lists the completed tasks of that Source and names the filter
  kind: product
  actor: user
  entities:
  - {entity: task, effect: reads, facts: [Name, Finished at]}
  - {entity: source, effect: reads, facts: [Name]}
  contexts:
    web:
      place: web::completed-tasks
---

# Browse completed tasks of one source

## Trigger

The User chooses View tasks on a Source page.

## Outcome

Only completed tasks of that Source are listed.
