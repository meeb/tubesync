---
kind: alternative
routes:
  web: Web
steps:
- text: A media item has metadata and no download task yet
  kind: condition
  unattended: true
  entities:
  - {entity: media, effect: reads, facts: [Available formats]}
  - {entity: task, effect: reads, facts: []}
  contexts:
    web:
      place: web::media-item
- text: The Product finds no format matching the Source and no fallback it allows
  kind: product
  entities:
  - {entity: source, effect: reads, facts: [Resolution, Video codec, Audio codec, Prefer 60fps, Prefer HDR, Audio track, Fallback]}
  - {entity: media, effect: changes, from: Fetching metadata, to: No matching formats, facts: [Can download]}
  contexts:
    web:
      place: web::media-item
---

# No format matches the source

## Trigger

A media item gets metadata but none of its formats suits the Source.

## Outcome

The media item cannot be downloaded and is listed as having no matching formats.
