---
kind: primary
routes:
  web: Web
steps:
- text: The User chooses Unskip media and confirms Enable and download media
  kind: actor
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [Title]}
  contexts:
    web:
      place: web::media-item
- text: The Product clears the skip and schedules its metadata to be fetched
  kind: product
  actor: user
  entities:
  - {entity: media, effect: changes, from: Manually skipped, to: Fetching metadata, facts: []}
  contexts:
    web:
      place: web::media-item
- text: The Product shows "Media has been re-enabled and will be downloaded"
  kind: product
  actor: user
  entities:
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::media-item
---

# Unskip a media item

## Trigger

The User wants a skipped media item after all.

## Outcome

The media item is no longer manually skipped and its metadata is fetched again before TubeSync decides to download it.
