---
kind: validation
routes:
  web: Web
steps:
- text: The User submits changed details
  kind: actor
  actor: user
  entities: []
  contexts:
    web:
      place: web::edit-media-server
- text: The test connection or library check fails
  kind: condition
  entities: []
  contexts:
    web:
      place: web::edit-media-server
- text: The Product refuses the form with the error
  kind: product
  actor: user
  entities:
  - {entity: media-server, effect: reads, facts: []}
  contexts:
    web:
      place: web::edit-media-server
---

# Refuse details that fail the test

## Trigger

The changed details fail the test connection or name an unknown library.

## Outcome

The media server keeps its previous details.
