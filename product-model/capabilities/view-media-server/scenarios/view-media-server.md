---
kind: primary
routes:
  web: Web
steps:
- text: The User opens a media server
  kind: actor
  actor: user
  entities:
  - {entity: media-server, effect: reads, facts: []}
  contexts:
    web:
      place: web::media-server
- text: The Product shows the media server type, address, HTTPS options and libraries, shortening the token
  kind: product
  actor: user
  entities:
  - {entity: media-server, effect: reads, facts: [Type, Host, Port, Use HTTPS, Verify HTTPS, Token, Libraries]}
  contexts:
    web:
      place: web::media-server
- text: The User reads the media server
  kind: actor
  actor: user
  entities:
  - {entity: media-server, effect: reads, facts: [Type, Host, Port, Libraries]}
  contexts:
    web:
      place: web::media-server
---

# Read a media server

## Trigger

The User opens a media server.

## Outcome

The User sees its settings with the token shortened.
