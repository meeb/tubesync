---
kind: alternative
routes:
  web: Web
steps:
- text: The User opens the dashboard
  kind: actor
  actor: user
  entities: []
  contexts:
    web:
      place: web::dashboard
- text: No Source exists yet
  kind: condition
  entities:
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::dashboard
- text: The Product says no media sources are added and offers Add a source
  kind: product
  actor: user
  entities:
  - {entity: source, effect: reads, facts: []}
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::dashboard
---

# Dashboard before any source

## Trigger

The User opens TubeSync before adding a Source.

## Outcome

The dashboard invites the User to add a Source.
