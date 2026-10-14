---
kind: alternative
routes:
  web: Web
steps:
- text: A media item has metadata and its Source has Download media off
  kind: condition
  unattended: true
  entities:
  - {entity: source, effect: reads, facts: [Download media]}
  - {entity: media, effect: reads, facts: [Available formats]}
  contexts:
    web:
      place: web::media-item
- text: The Product schedules no download and lists the media item as disabled at source
  kind: product
  entities:
  - {entity: media, effect: changes, from: Fetching metadata, to: Disabled at source, facts: [Can download]}
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::media-item
---

# The source does not download media

## Trigger

A media item of a Source that only indexes gets its metadata.

## Outcome

The media item is listed as disabled at source and no download is scheduled.

## Edge cases

- A downloaded file that has disappeared from disk marks its media skipped instead of downloading it again.
