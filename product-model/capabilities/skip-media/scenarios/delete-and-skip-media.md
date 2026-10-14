---
kind: alternative
routes:
  web: Web
steps:
- text: The User chooses Delete and skip media and confirms
  kind: actor
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [Title, File path]}
  contexts:
    web:
      place: web::media-item
- text: The Product deletes the file and every file saved beside it, then marks the media item manually skipped
  kind: product
  actor: user
  entities:
  - {entity: media, effect: changes, from: Downloaded, to: Manually skipped, facts: [Download date, Downloaded format, Downloaded codecs, Container, Downloaded FPS, Downloaded HDR, File size, File path]}
  contexts:
    web:
      place: web::media-item
- text: The Product shows "Media file has been deleted and marked to never download"
  kind: product
  actor: user
  entities:
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::media-item
---

# Delete and skip downloaded media

## Trigger

The User no longer wants a local copy of a downloaded media item.

## Outcome

The file and the files saved beside it are deleted and the media item is manually skipped.
