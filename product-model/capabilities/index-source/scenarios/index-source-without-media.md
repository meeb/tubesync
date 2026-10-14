---
kind: edge
routes:
  web: Web
steps:
- text: YouTube returns no media for the Source
  kind: condition
  unattended: true
  entities:
  - {entity: source, effect: reads, facts: [Key]}
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::source
- text: The Product marks the Source as failed
  kind: product
  entities:
  - {entity: source, effect: changes, facts: [Has failed]}
  contexts:
    web:
      place: web::source
- text: The Product fails the indexing task asking to check the Source key and configuration
  kind: product
  entities:
  - {entity: task, effect: changes, from: Running, to: Failed, facts: [Last error, Attempts]}
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::source
---

# A source returns no media

## Trigger

Indexing a Source returns no media at all.

## Outcome

The Source is marked as failed and the indexing task records the error.
