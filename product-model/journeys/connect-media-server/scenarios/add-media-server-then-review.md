---
kind: primary
result: achieved
routes:
  web: Web
steps:
- text: The User enters the Plex server details
  kind: actor
  actor: user
  entities: []
  contexts:
    web:
      place: web::add-media-server
- text: The Product tests and saves the media server and opens its page
  kind: product
  actor: user
  entities:
  - {entity: media-server, effect: creates, facts: [Type, Host, Port, Use HTTPS, Verify HTTPS, Token, Libraries]}
  contexts:
    web:
      place: web::media-server
  capability: add-media-server
- text: The User reads the media server details
  kind: actor
  actor: user
  entities:
  - {entity: media-server, effect: reads, facts: [Type, Host, Port, Libraries]}
  contexts:
    web:
      place: web::media-server
  capability: view-media-server
---

# Add a Plex server and review it

## Trigger

The User wants Plex refreshed when media downloads.

## Outcome

The User is on the new media server page.
