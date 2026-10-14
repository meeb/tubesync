---
kind: primary
routes:
  web: Web
steps:
- text: At forty minutes past the hour a media item awaiting its premiere has passed its published time
  kind: condition
  unattended: true
  entities:
  - {entity: media, effect: reads, facts: [Published]}
  contexts:
    web:
      place: web::media-item
- text: The Product releases the media item and schedules its metadata
  kind: product
  entities:
  - {entity: media, effect: changes, from: Awaiting premiere, to: Fetching metadata, facts: []}
  contexts:
    web:
      place: web::media-item
---

# Release a started premiere

## Trigger

The premiere time of a media item has passed.

## Outcome

The media item is no longer held and its metadata is fetched.

## Edge cases

- A premiere still in the future shows how many hours remain in its title.
