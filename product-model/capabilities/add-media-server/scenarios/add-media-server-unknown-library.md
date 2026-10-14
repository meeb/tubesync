---
kind: validation
routes:
  web: Web
steps:
- text: The User submits library IDs that include one the server does not have
  kind: actor
  actor: user
  entities: []
  contexts:
    web:
      place: web::add-media-server
- text: The Product refuses the form and lists the valid libraries with their IDs
  kind: product
  actor: user
  entities: []
  contexts:
    web:
      place: web::add-media-server
---

# Refuse a library the server does not have

## Trigger

A listed library ID does not exist on the server.

## Outcome

Nothing is saved and the form lists the libraries the server has.

## Edge cases

- A host and port already used by another media server is refused.
