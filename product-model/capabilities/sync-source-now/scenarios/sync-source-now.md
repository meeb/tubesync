---
kind: primary
routes:
  web: Web
steps:
- text: The User chooses Sync Now on a Source
  kind: actor
  actor: user
  entities:
  - {entity: source, effect: reads, facts: [Name]}
  contexts:
    web:
      place: web::sources
- text: The Product schedules a one-off indexing of the Source
  kind: product
  actor: user
  entities:
  - {entity: task, effect: creates, to: Scheduled, facts: [Name, Scheduled at]}
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::sources
- text: The Product shows "The source has been scheduled to be synced now."
  kind: product
  actor: user
  entities:
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::sources
---

# Sync a source now

## Trigger

The User does not want to wait for the next scheduled indexing.

## Outcome

A one-off indexing of the Source is scheduled and the User is told so.
