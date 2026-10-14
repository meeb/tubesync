---
kind: primary
routes:
  web: Web
steps:
- text: A media item is waiting to download and still passes the download checks
  kind: condition
  unattended: true
  entities:
  - {entity: media, effect: reads, facts: [Matched formats, Published]}
  - {entity: source, effect: reads, facts: [Download media, Download cap]}
  contexts:
    web:
      place: web::media-item
- text: The Product downloads the matched format with the Source options for SponsorBlock, subtitles and embedding
  kind: product
  entities:
  - {entity: source, effect: reads, facts: [SponsorBlock, SponsorBlock categories, Write subtitles, Auto-generated subtitles, Subtitle languages, Embed metadata, Embed thumbnail, Write JSON]}
  contexts:
    web:
      place: web::media-item
- text: The Product records where and in what format the media was saved
  kind: product
  entities:
  - {entity: media, effect: changes, from: Downloading, to: Downloaded, facts: [Download date, Downloaded format, Downloaded codecs, Container, Downloaded FPS, Downloaded HDR, File size, File path]}
  contexts:
    web:
      place: web::media-item
- text: The Product copies the thumbnail and writes an NFO file beside the media when the Source asks for them
  kind: product
  entities:
  - {entity: source, effect: reads, facts: [Copy thumbnails, Write NFO]}
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::media-item
- text: The Product asks every media server to refresh its libraries
  kind: product
  entities:
  - {entity: media-server, effect: reads, facts: [Libraries]}
  contexts:
    web:
      place: web::media-item
---

# Download a media item

## Trigger

A media item is waiting to download and its task runs.

## Outcome

The file is saved at its media format path, the media item is downloaded, and media servers are asked to refresh.

## Edge cases

- Media skipped, already downloaded, too old for the download cap, or of a Source that stopped downloading since it was queued is not downloaded.
- A download running longer than the maximum run time is stopped.
