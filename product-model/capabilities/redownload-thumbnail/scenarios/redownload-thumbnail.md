---
kind: primary
routes:
  web: Web
steps:
- text: The User chooses the redo control on the thumbnail
  kind: actor
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [Thumbnail]}
  contexts:
    web:
      place: web::media-item
- text: The Product schedules the thumbnail download with raised priority and says so
  kind: product
  actor: user
  entities:
  - {entity: task, effect: creates, to: Scheduled, facts: [Name, Scheduled at, Priority]}
  contexts:
    web:
      place: web::media-item
- text: The Product downloads the thumbnail, resizes it and replaces the kept thumbnail
  kind: product
  entities:
  - {entity: media, effect: changes, facts: [Thumbnail]}
  contexts:
    web:
      place: web::media-item
---

# Redownload a thumbnail

## Trigger

The User wants a fresh thumbnail for a media item.

## Outcome

A thumbnail download is scheduled ahead of others and replaces the kept thumbnail.

## Edge cases

- Skipped media gets no thumbnail.
- A thumbnail YouTube no longer has leaves the media without one.
