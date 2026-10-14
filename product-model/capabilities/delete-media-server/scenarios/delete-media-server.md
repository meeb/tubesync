---
kind: primary
routes:
  web: Web
steps:
- text: The User chooses Delete media server and confirms
  kind: actor
  actor: user
  entities:
  - {entity: media-server, effect: reads, facts: [Host, Port]}
  contexts:
    web:
      place: web::media-server
- text: The Product deletes the media server and shows "Your selected media server has been deleted."
  kind: product
  actor: user
  entities:
  - {entity: media-server, effect: removes}
  contexts:
    web:
      place: web::media-servers
---

# Delete a media server

## Trigger

The User no longer wants a media server notified.

## Outcome

The media server is gone and the User is back on the media server list.
