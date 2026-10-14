---
kind: alternative
routes:
  web: Web
steps:
- text: The User changes the index schedule or target schedule and saves
  kind: actor
  actor: user
  entities: []
  contexts:
    web:
      place: web::edit-source
- text: The Product saves the Source schedule
  kind: product
  actor: user
  entities:
  - {entity: source, effect: changes, facts: [Index schedule, Target schedule]}
  contexts:
    web:
      place: web::source
- text: The Product replaces the scheduled indexing of the Source with one at the new target time
  kind: product
  actor: user
  entities:
  - {entity: task, effect: creates, to: Scheduled, facts: [Name, Scheduled at]}
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::source
---

# Change how often a source is indexed

## Trigger

The User changes the index schedule or name of a Source.

## Outcome

The next indexing of the Source is rescheduled to its new target time.
