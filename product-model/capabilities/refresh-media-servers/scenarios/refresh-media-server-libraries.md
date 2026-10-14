---
kind: primary
routes:
  web: Web
steps:
- text: Media was downloaded, or expired or missing media was removed
  kind: condition
  unattended: true
  entities:
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::media-servers
- text: The Product asks each media server to refresh each listed library
  kind: product
  entities:
  - {entity: media-server, effect: reads, facts: [Type, Host, Port, Libraries]}
  contexts:
    web:
      place: web::media-servers
---

# Refresh media server libraries

## Trigger

Media was downloaded or removed.

## Outcome

Each media server has been asked to refresh each of its listed libraries.

## Edge cases

- A refresh not started within a few minutes of being scheduled is dropped.
