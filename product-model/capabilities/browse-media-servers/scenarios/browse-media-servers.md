---
kind: primary
routes:
  web: Web
steps:
- text: The User opens the Media Servers page
  kind: actor
  actor: user
  entities:
  - {entity: media-server, effect: reads, facts: []}
  contexts:
    web:
      place: web::media-servers
- text: The Product lists each media server by host and port with its type
  kind: product
  actor: user
  entities:
  - {entity: media-server, effect: reads, facts: [Type, Host, Port, Use HTTPS]}
  contexts:
    web:
      place: web::media-servers
- text: The User reads the media servers
  kind: actor
  actor: user
  entities:
  - {entity: media-server, effect: reads, facts: [Type, Host, Port]}
  contexts:
    web:
      place: web::media-servers
---

# Browse media servers

## Trigger

The User opens the Media Servers page.

## Outcome

The User sees each media server by type and address.
