---
kind: edge
routes:
  web: Web
steps:
- text: YouTube returns details for the media item without any formats
  kind: condition
  unattended: true
  entities:
  - {entity: media, effect: reads, facts: [Key]}
  contexts:
    web:
      place: web::media-item
- text: The Product marks the media item as not downloadable and skipped
  kind: product
  entities:
  - {entity: media, effect: changes, from: Fetching metadata, to: Skipped by system, facts: [Can download]}
  contexts:
    web:
      place: web::media-item
---

# Media offers no formats

## Trigger

YouTube returns no formats for a media item, for example members-only media.

## Outcome

The media item is skipped by the system as not downloadable.
