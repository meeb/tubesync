---
kind: primary
routes:
  web: Web
steps:
- text: The User opens a Source
  kind: actor
  actor: user
  entities:
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::source
- text: The Product shows the Source settings, an example file name, last crawl and target schedule
  kind: product
  actor: user
  entities:
  - {entity: source, effect: reads, facts: [Type, Key, Name, Directory, Filter text, Invert filter text, Filter seconds, Filter seconds mode, Media format, Target schedule, Index schedule, Index videos, Index streams, Download media, Download cap, Delete old media, Days to keep, Resolution, Video codec, Audio codec, Prefer 60fps, Prefer HDR, Audio track, Fallback, Delete removed media, Delete files on disk, Copy channel images, Copy thumbnails, Write NFO, Write JSON, Embed metadata, Embed thumbnail, SponsorBlock, SponsorBlock categories, Write subtitles, Auto-generated subtitles, Subtitle languages, Created, Last crawl, Has failed]}
  contexts:
    web:
      place: web::source
- text: The Product lists the failed tasks for the Source with their errors
  kind: product
  actor: user
  entities:
  - {entity: task, effect: reads, facts: [Name, Last error, Started at]}
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::source
- text: The User reads the Source and its errors
  kind: actor
  actor: user
  entities:
  - {entity: source, effect: reads, facts: [Name, Directory, Last crawl, Target schedule, Has failed]}
  - {entity: task, effect: reads, facts: [Name, Last error]}
  contexts:
    web:
      place: web::source
---

# Read a source

## Trigger

The User opens a Source from the Sources page.

## Outcome

The User sees the Source settings, its last crawl and target schedule, and any errors.

## Edge cases

- A Source with permanent failures shows a warning to check its settings.
