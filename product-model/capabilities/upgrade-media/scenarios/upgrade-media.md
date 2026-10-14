---
kind: primary
routes:
  web: Web
steps:
- text: A downloaded video now has a matching format with a greater height than the saved file
  kind: condition
  unattended: true
  entities:
  - {entity: media, effect: reads, facts: [Downloaded format, Matched formats]}
  - {entity: deployment-settings, effect: reads, facts: [Upgrade media]}
  contexts:
    web:
      place: web::media-item
- text: The Product downloads the better format and replaces the saved file
  kind: product
  entities:
  - {entity: media, effect: changes, from: Downloaded, to: Downloaded, facts: [Download date, Downloaded format, Downloaded codecs, Container, Downloaded FPS, Downloaded HDR, File size, File path]}
  contexts:
    web:
      place: web::media-item
---

# Upgrade to a better format

## Trigger

A video was downloaded and a format with greater height now matches.

## Outcome

The media item is downloaded again in the better format.

## Edge cases

- Audio-only media is never upgraded.
- When the saved file is as good, nothing is downloaded; the attempt is repeated up to six times an hour apart.
