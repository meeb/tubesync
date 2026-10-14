---
kind: primary
routes:
  web: Web
steps:
- text: A media item has no kept thumbnail and is not skipped
  kind: condition
  unattended: true
  entities:
  - {entity: media, effect: reads, facts: [Key]}
  contexts:
    web:
      place: web::media
- text: The Product downloads the available thumbnail images and keeps the best one, resized to fit 430 by 240
  kind: product
  entities:
  - {entity: media, effect: changes, facts: [Thumbnail]}
  contexts:
    web:
      place: web::media
- text: The Product copies the thumbnail next to the downloaded file when the Source copies thumbnails
  kind: product
  entities:
  - {entity: source, effect: reads, facts: [Copy thumbnails]}
  contexts:
    web:
      place: web::media
---

# Keep a thumbnail for new media

## Trigger

A new media item has no thumbnail.

## Outcome

The media item has its best available thumbnail, at most 430 by 240 pixels.

## Edge cases

- Media without any thumbnail shows a placeholder image.
