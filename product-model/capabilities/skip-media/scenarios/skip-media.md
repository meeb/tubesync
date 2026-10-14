---
kind: primary
routes:
  web: Web
steps:
- text: The User chooses Manually mark media to be skipped and confirms
  kind: actor
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [Title]}
  contexts:
    web:
      place: web::media-item
- text: The Product marks the media item manually skipped and clears its metadata
  kind: product
  actor: user
  entities:
  - {entity: media, effect: changes, from: Downloading, to: Manually skipped, facts: [Available formats, Description]}
  contexts:
    web:
      place: web::media-item
- text: The Product shows that the media has been marked to never download
  kind: product
  actor: user
  entities:
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::media-item
---

# Skip media before it is downloaded

## Trigger

The User does not want a media item that is waiting to download.

## Outcome

The media item is manually skipped and will not be downloaded.
