---
kind: primary
routes:
  web: Web
steps:
- text: The User opens a media item
  kind: actor
  actor: user
  entities:
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::media-item
- text: The Product shows the media details, the desired format and fallback of its Source, available and matched formats
  kind: product
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [Key, Title, Description, Published, Duration, Thumbnail, Available formats, Matched formats, Can download, Download date, Downloaded format, Downloaded codecs, Container, Downloaded FPS, Downloaded HDR, File size, File path]}
  - {entity: source, effect: reads, facts: [Name, Directory, Resolution, Video codec, Audio codec, Prefer 60fps, Prefer HDR, Audio track, Fallback]}
  contexts:
    web:
      place: web::media-item
- text: The Product shows the download task waiting or running for it
  kind: product
  actor: user
  entities:
  - {entity: task, effect: reads, facts: [Name, Scheduled at, Started at]}
  contexts:
    web:
      place: web::media-item
- text: The User reads the media item and its matched formats
  kind: actor
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [Title, Description, Available formats, Matched formats, Can download]}
  contexts:
    web:
      place: web::media-item
---

# Read a media item

## Trigger

The User opens a media item.

## Outcome

The User sees its details, matched formats, download state and any running or waiting download task.
