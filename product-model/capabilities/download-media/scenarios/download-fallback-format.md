---
kind: alternative
routes:
  web: Web
steps:
- text: No format exactly matches the Source resolution and codecs
  kind: condition
  unattended: true
  entities:
  - {entity: media, effect: reads, facts: [Available formats]}
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::media-item
- text: The Product picks the next best format the Source fallback allows
  kind: product
  entities:
  - {entity: source, effect: reads, facts: [Fallback, Resolution, Video codec]}
  contexts:
    web:
      place: web::media-item
- text: The Product downloads that format and records it
  kind: product
  entities:
  - {entity: media, effect: changes, from: Downloading, to: Downloaded, facts: [Download date, Downloaded format, Downloaded codecs, Container, Downloaded FPS, Downloaded HDR, File size, File path]}
  contexts:
    web:
      place: web::media-item
---

# Download a fallback format

## Trigger

No format of a media item exactly matches the Source.

## Outcome

The media item downloads in the next best format its Source fallback allows.

## Decision points

### Which fallback applies?

What does the Source fallback allow?

- Get next best resolution, any codec → the best lower resolution in any codec
- Get next best resolution, only the preferred codec → the best lower resolution in the Source video codec
- Get next best resolution, any codec, but at least HD → the best lower resolution of at least HD height
