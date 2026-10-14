---
kind: primary
routes:
  web: Web
steps:
- text: A media item is waiting for metadata and is not manually skipped
  kind: condition
  unattended: true
  entities:
  - {entity: media, effect: reads, facts: [Key]}
  contexts:
    web:
      place: web::media-item
- text: The Product fetches the media details and formats from YouTube
  kind: product
  entities:
  - {entity: media, effect: reads, facts: [Key]}
  contexts:
    web:
      place: web::media-item
- text: The Product keeps the title, description, published time, duration and available formats
  kind: product
  entities:
  - {entity: media, effect: changes, facts: [Title, Description, Published, Duration, Available formats]}
  contexts:
    web:
      place: web::media-item
---

# Fetch metadata for new media

## Trigger

A media item is waiting for metadata.

## Outcome

The media item has its title, description, published time, duration and available formats.

## Edge cases

- A failed fetch is retried up to three times, ten minutes apart.
