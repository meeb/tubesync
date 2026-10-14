---
kind: edge
routes:
  web: Web
steps:
- text: The download fails or the expected file is missing afterwards
  kind: condition
  unattended: true
  entities:
  - {entity: media, effect: reads, facts: [Matched formats]}
  contexts:
    web:
      place: web::media-item
- text: The Product drops a format that did not work and schedules its formats to be refreshed
  kind: product
  entities:
  - {entity: media, effect: changes, facts: [Available formats]}
  - {entity: task, effect: creates, to: Scheduled, facts: [Name, Scheduled at]}
  contexts:
    web:
      place: web::media-item
---

# A download fails

## Trigger

Downloading a media item fails, or the chosen format is no longer offered.

## Outcome

The media item stays waiting to download while its formats are refreshed and a new attempt follows.

## Edge cases

- While YouTube answers "Too Many Requests" the download waits before trying.
