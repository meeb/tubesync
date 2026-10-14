---
kind: primary
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
- text: The Product finds a format matching the Source resolution, codecs and preferences, or a fallback it allows
  kind: product
  entities:
  - {entity: source, effect: reads, facts: [Resolution, Video codec, Audio codec, Prefer 60fps, Prefer HDR, Audio track, Fallback]}
  - {entity: media, effect: changes, facts: [Can download, Matched formats]}
  contexts:
    web:
      place: web::media-item
- text: The Product finds that no filter of the Source skips the media item and schedules its download
  kind: product
  entities:
  - {entity: source, effect: reads, facts: [Download media, Filter text, Invert filter text, Filter seconds, Filter seconds mode, Download cap]}
  - {entity: media, effect: changes, from: Fetching metadata, to: Downloading, facts: []}
  - {entity: task, effect: creates, to: Scheduled, facts: [Name, Scheduled at]}
  contexts:
    web:
      place: web::media-item
---

# Media matches its source

## Trigger

A media item gets its metadata.

## Outcome

A format matches, no filter skips it, and its download is scheduled.
