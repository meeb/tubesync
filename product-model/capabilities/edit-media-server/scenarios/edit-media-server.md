---
kind: primary
routes:
  web: Web
steps:
- text: The User chooses Edit media server, changes details and submits
  kind: actor
  actor: user
  entities:
  - {entity: media-server, effect: reads, facts: []}
  contexts:
    web:
      place: web::edit-media-server
- text: The Product tests the connection and the libraries
  kind: product
  actor: user
  entities: []
  contexts:
    web:
      place: web::edit-media-server
- text: The Product saves the media server
  kind: product
  actor: user
  entities:
  - {entity: media-server, effect: changes, facts: [Host, Port, Use HTTPS, Verify HTTPS, Token, Libraries]}
  contexts:
    web:
      place: web::media-server
---

# Change a media server

## Trigger

The User changes the address, token or libraries of a media server.

## Outcome

The media server keeps the new details after a successful test.
