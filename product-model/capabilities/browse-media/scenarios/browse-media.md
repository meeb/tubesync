---
kind: primary
routes:
  web: Web
steps:
- text: The User opens the Media page
  kind: actor
  actor: user
  entities:
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::media
- text: The Product lists media that can be downloaded and is not skipped, newest published first
  kind: product
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [Title, Thumbnail, Download date, Published, Can download]}
  contexts:
    web:
      place: web::media
- text: The User reads each media item and whether it is downloaded, downloading or fetching metadata
  kind: actor
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [Title, Thumbnail, Download date]}
  contexts:
    web:
      place: web::media
---

# Browse downloadable media

## Trigger

The User opens the Media page.

## Outcome

The User sees media that can be downloaded, newest first, each with its state.

## Edge cases

- With nothing indexed the page says no media has been indexed.
