---
kind: primary
routes:
  web: Web
steps:
- text: The User chooses Download on a downloaded media item
  kind: actor
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [File path]}
  contexts:
    web:
      place: web::media-item
- text: The Product sends the saved file under its file name
  kind: product
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [File path, Container]}
  contexts:
    web:
      place: web::media-item
---

# Save a media file

## Trigger

The User wants a copy of a downloaded media file.

## Outcome

The browser saves the file under its media file name.
