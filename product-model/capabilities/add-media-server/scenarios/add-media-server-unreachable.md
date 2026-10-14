---
kind: validation
routes:
  web: Web
steps:
- text: The User submits the media server details
  kind: actor
  actor: user
  entities:
  - {entity: media-server, effect: reads, facts: []}
  contexts:
    web:
      place: web::add-media-server
- text: The test connection fails or returns an error status
  kind: condition
  entities: []
  contexts:
    web:
      place: web::add-media-server
- text: The Product refuses the form with the error, suggesting the host, port or token be checked
  kind: product
  actor: user
  entities: []
  contexts:
    web:
      place: web::add-media-server
---

# Refuse a server that cannot be reached

## Trigger

The test connection fails or the server rejects the token.

## Outcome

Nothing is saved and the form explains what failed.
