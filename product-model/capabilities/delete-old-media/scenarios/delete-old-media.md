---
kind: primary
routes:
  web: Web
steps:
- text: A Source deletes old media and a media item was downloaded more than its days to keep ago
  kind: condition
  unattended: true
  entities:
  - {entity: source, effect: reads, facts: [Delete old media, Days to keep, Delete files on disk]}
  - {entity: media, effect: reads, facts: [Download date]}
  contexts:
    web:
      place: web::media
- text: The Product deletes the file and the files saved beside it and removes the media item, remembering it as skipped
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

# Delete expired media and its files

## Trigger

Media of a Source that deletes old media and files on disk was downloaded longer ago than the days to keep.

## Outcome

The media and its files are gone, the item is remembered as skipped, and media servers are asked to refresh.
