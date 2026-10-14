---
kind: alternative
routes:
  web: Web
steps:
- text: The User chooses Add a Jellyfin media server
  kind: actor
  actor: user
  entities:
  - {entity: media-server, effect: reads, facts: []}
  contexts:
    web:
      place: web::media-servers
- text: The User enters host, port, HTTPS options, API key token and library IDs and submits
  kind: actor
  actor: user
  entities: []
  contexts:
    web:
      place: web::add-media-server
- text: The Product connects to the Jellyfin server and confirms every library ID exists there
  kind: product
  actor: user
  entities: []
  contexts:
    web:
      place: web::add-media-server
- text: The Product saves the media server and opens it
  kind: product
  actor: user
  entities:
  - {entity: media-server, effect: creates, facts: [Type, Host, Port, Use HTTPS, Verify HTTPS, Token, Libraries]}
  contexts:
    web:
      place: web::media-server
---

# Add a Jellyfin server

## Trigger

The User wants Jellyfin libraries refreshed when media downloads.

## Outcome

The Jellyfin server is saved.

## Edge cases

- Leaving the libraries blank is refused with the list of the server libraries and their IDs.
