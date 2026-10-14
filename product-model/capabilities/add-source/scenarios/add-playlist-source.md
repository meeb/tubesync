---
kind: alternative
routes:
  web: Web
steps:
- text: The User enters a playlist URL such as https://www.youtube.com/playlist?list=ID
  kind: actor
  actor: user
  entities: []
  contexts:
    web:
      place: web::add-source
- text: The Product recognises a playlist URL and prefills type playlist and the playlist ID as key
  kind: product
  actor: user
  entities: []
  contexts:
    web:
      place: web::add-source
- text: The User completes the Source settings and adds the Source
  kind: actor
  actor: user
  entities:
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::add-source
- text: The Product creates the Source and schedules its first indexing
  kind: product
  actor: user
  entities:
  - {entity: source, effect: creates, to: Active, facts: [Type, Key, Name, Directory, Filter text, Invert filter text, Filter seconds, Filter seconds mode, Media format, Target schedule, Index schedule, Index videos, Index streams, Download media, Download cap, Delete old media, Days to keep, Resolution, Video codec, Audio codec, Prefer 60fps, Prefer HDR, Audio track, Fallback, Delete removed media, Delete files on disk, Copy channel images, Copy thumbnails, Write NFO, Write JSON, Embed metadata, Embed thumbnail, SponsorBlock, SponsorBlock categories, Write subtitles, Auto-generated subtitles, Subtitle languages, Created]}
  contexts:
    web:
      place: web::source
---

# Add a playlist

## Trigger

The User wants a YouTube playlist kept in sync.

## Outcome

A new active Source of type playlist exists with the playlist ID as its key.
