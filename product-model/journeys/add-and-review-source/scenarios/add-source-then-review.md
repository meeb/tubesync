---
kind: primary
result: achieved
routes:
  web: Web
steps:
- text: The User enters a channel URL and completes the Source settings
  kind: actor
  actor: user
  entities:
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::add-source
- text: The Product creates the Source and opens its page
  kind: product
  actor: user
  entities:
  - {entity: source, effect: creates, to: Active, facts: [Type, Key, Name, Directory, Filter text, Invert filter text, Filter seconds, Filter seconds mode, Media format, Target schedule, Index schedule, Index videos, Index streams, Download media, Download cap, Delete old media, Days to keep, Resolution, Video codec, Audio codec, Prefer 60fps, Prefer HDR, Audio track, Fallback, Delete removed media, Delete files on disk, Copy channel images, Copy thumbnails, Write NFO, Write JSON, Embed metadata, Embed thumbnail, SponsorBlock, SponsorBlock categories, Write subtitles, Auto-generated subtitles, Subtitle languages, Created]}
  contexts:
    web:
      place: web::source
  capability: add-source
- text: The User reads the settings of the new Source
  kind: actor
  actor: user
  entities:
  - {entity: source, effect: reads, facts: [Name, Directory, Target schedule]}
  contexts:
    web:
      place: web::source
  capability: view-source
---

# Add a channel and review it

## Trigger

The User wants a new channel kept in sync.

## Outcome

The User is on the new Source page, reading its settings and the note that media may take a while to appear.
