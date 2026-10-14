---
kind: alternative
routes:
  web: Web
steps:
- text: A Source deletes old media but not files on disk, and a media item has expired
  kind: condition
  unattended: true
  entities:
  - {entity: source, effect: reads, facts: [Delete old media, Days to keep, Delete files on disk]}
  - {entity: media, effect: reads, facts: [Download date]}
  contexts:
    web:
      place: web::media
- text: The Product removes the media item from TubeSync, remembering it as skipped, and leaves its files on disk
  kind: product
  entities:
  - {entity: media, effect: changes, from: Downloaded, to: Manually skipped, facts: [Download date]}
  contexts:
    web:
      place: web::media
---

# Expire media but keep its files

## Trigger

Media of a Source that deletes old media, but not files on disk, has expired.

## Outcome

The media item is removed from TubeSync and remembered as skipped; its files stay on disk.

## Edge cases

- Media busy in another task is retried later.
