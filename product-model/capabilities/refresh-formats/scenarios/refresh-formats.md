---
kind: primary
routes:
  web: Web
steps:
- text: A media item has no matching format and its formats were not refreshed within its Source index schedule
  kind: condition
  unattended: true
  entities:
  - {entity: media, effect: reads, facts: [Available formats]}
  - {entity: source, effect: reads, facts: [Index schedule]}
  contexts:
    web:
      place: web::media-item
- text: The Product fetches the current formats, thumbnails and availability from YouTube
  kind: product
  entities:
  - {entity: media, effect: changes, facts: [Available formats, Thumbnail]}
  contexts:
    web:
      place: web::media-item
- text: The Product checks the media item again and a format now matches
  kind: product
  entities:
  - {entity: media, effect: changes, from: No matching formats, to: Downloading, facts: [Can download, Matched formats]}
  contexts:
    web:
      place: web::media-item
---

# New formats let media download

## Trigger

A media item has no matching format, or its download failed.

## Outcome

The media item has current formats and, when one matches, is waiting to download.
