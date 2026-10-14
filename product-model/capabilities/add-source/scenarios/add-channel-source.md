---
kind: primary
routes:
  web: Web
steps:
- text: The User enters a channel URL such as https://www.youtube.com/@name
  kind: actor
  actor: user
  entities: []
  contexts:
    web:
      place: web::add-source
- text: The Product recognises a channel URL and resolves the handle to the channel ID
  kind: product
  actor: user
  entities: []
  contexts:
    web:
      place: web::add-source
- text: The Product prefills the Source form with type channel by ID, the key and the default media format
  kind: product
  actor: user
  entities:
  - {entity: source, effect: reads, facts: []}
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::add-source
- text: The User sets the name, directory, schedule, filters, format and file options and adds the Source
  kind: actor
  actor: user
  entities:
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::add-source
- text: The Product creates the Source
  kind: product
  actor: user
  entities:
  - {entity: source, effect: creates, to: Active, facts: [Type, Key, Name, Directory, Filter text, Invert filter text, Filter seconds, Filter seconds mode, Media format, Target schedule, Index schedule, Index videos, Index streams, Download media, Download cap, Delete old media, Days to keep, Resolution, Video codec, Audio codec, Prefer 60fps, Prefer HDR, Audio track, Fallback, Delete removed media, Delete files on disk, Copy channel images, Copy thumbnails, Write NFO, Write JSON, Embed metadata, Embed thumbnail, SponsorBlock, SponsorBlock categories, Write subtitles, Auto-generated subtitles, Subtitle languages, Created]}
  contexts:
    web:
      place: web::source
- text: The Product creates the Source directory and schedules its first indexing for ten minutes later
  kind: product
  actor: user
  entities:
  - {entity: source, effect: reads, facts: [Directory, Index schedule]}
  contexts:
    web:
      place: web::source
- text: The Product opens the new Source with a note that large channels can take up to an hour to appear
  kind: product
  actor: user
  entities:
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::source
---

# Add a channel by its handle

## Trigger

The User wants a YouTube channel kept in sync.

## Outcome

A new active Source exists for the channel, its directory exists, and its first indexing is scheduled; the User is on its page.

## Edge cases

- A handle that cannot be resolved to a channel ID keeps the channel type with the handle as its key.
- A name, key or directory another Source already uses is refused on the form.
