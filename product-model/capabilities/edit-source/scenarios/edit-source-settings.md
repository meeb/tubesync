---
kind: primary
routes:
  web: Web
steps:
- text: The User opens Edit source and changes settings
  kind: actor
  actor: user
  entities:
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::edit-source
- text: The Product saves the Source settings
  kind: product
  actor: user
  entities:
  - {entity: source, effect: changes, facts: [Type, Key, Name, Directory, Filter text, Invert filter text, Filter seconds, Filter seconds mode, Media format, Target schedule, Index schedule, Index videos, Index streams, Download media, Download cap, Delete old media, Days to keep, Resolution, Video codec, Audio codec, Prefer 60fps, Prefer HDR, Audio track, Fallback, Delete removed media, Delete files on disk, Copy channel images, Copy thumbnails, Write NFO, Write JSON, Embed metadata, Embed thumbnail, SponsorBlock, SponsorBlock categories, Write subtitles, Auto-generated subtitles, Subtitle languages]}
  contexts:
    web:
      place: web::source
- text: The Product schedules a check of all media for the Source and opens it with "Your source has been updated."
  kind: product
  actor: user
  entities:
  - {entity: source, effect: reads, facts: []}
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::source
---

# Change a source settings

## Trigger

The User wants different quality, filters or file options for a Source.

## Outcome

The Source keeps the new settings and a check of all its media is scheduled.

## Edge cases

- Turning Copy channel images on schedules the channel images to be copied.
