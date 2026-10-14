---
kind: alternative
routes:
  web: Web
steps:
- text: The Source deletes removed media and a downloaded media item is no longer listed
  kind: condition
  unattended: true
  entities:
  - {entity: source, effect: reads, facts: [Delete removed media, Delete files on disk]}
  - {entity: media, effect: reads, facts: [Key]}
  contexts:
    web:
      place: web::source
- text: The Product removes the media item and remembers it as skipped so it is not downloaded again
  kind: product
  entities:
  - {entity: media, effect: changes, from: Downloaded, to: Manually skipped, facts: [File path, Download date]}
  contexts:
    web:
      place: web::media
- text: The Product asks every media server to refresh its libraries
  kind: product
  entities:
  - {entity: media-server, effect: reads, facts: [Libraries]}
  contexts:
    web:
      place: web::media
---

# Remove media no longer on the source

## Trigger

Indexing a Source that deletes removed media no longer lists some of its media.

## Outcome

That media is removed from TubeSync and remembered as skipped; its files go only when the Source deletes files on disk.

## Edge cases

- Media busy in another task is removed by a later task instead.
