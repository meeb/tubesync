---
kind: primary
routes:
  web: Web
steps:
- text: The User chooses Redownload media and confirms
  kind: actor
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [Title, File path]}
  contexts:
    web:
      place: web::media-item
- text: The Product deletes the file, its copied thumbnail and NFO file, and the kept thumbnail
  kind: product
  actor: user
  entities:
  - {entity: media, effect: changes, from: Downloaded, to: Downloading, facts: [Download date, Downloaded format, Downloaded codecs, Container, Downloaded FPS, Downloaded HDR, File size, File path, Thumbnail]}
  contexts:
    web:
      place: web::media-item
- text: The Product refreshes the available formats and schedules the download to start shortly
  kind: product
  actor: user
  entities:
  - {entity: task, effect: creates, to: Scheduled, facts: [Name, Scheduled at, Priority]}
  contexts:
    web:
      place: web::media-item
- text: The Product shows "Media file has been deleted and scheduled to redownload"
  kind: product
  actor: user
  entities:
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::media-item
---

# Redownload a media item

## Trigger

The User wants a downloaded media item downloaded again.

## Outcome

The old file is gone and the media item is downloading again.
