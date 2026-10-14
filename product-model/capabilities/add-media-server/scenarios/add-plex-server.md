---
kind: primary
routes:
  web: Web
steps:
- text: The User chooses Add a Plex media server
  kind: actor
  actor: user
  entities:
  - {entity: media-server, effect: reads, facts: []}
  contexts:
    web:
      place: web::media-servers
- text: The User enters host, port, HTTPS options, Plex token and library IDs and submits
  kind: actor
  actor: user
  entities: []
  contexts:
    web:
      place: web::add-media-server
- text: The Product connects to the Plex server and confirms every library ID exists there
  kind: product
  actor: user
  entities: []
  contexts:
    web:
      place: web::add-media-server
- text: The Product saves the media server and opens it with "Your media server has been successfully added"
  kind: product
  actor: user
  entities:
  - {entity: media-server, effect: creates, facts: [Type, Host, Port, Use HTTPS, Verify HTTPS, Token, Libraries]}
  contexts:
    web:
      place: web::media-server
---

# Add a Plex server

## Trigger

The User wants Plex libraries refreshed when media downloads.

## Outcome

The Plex server is saved and the User is on its page.
