---
kind: primary
routes:
  web: Web
steps:
- text: The media item is skipped by the system but a format matches
  kind: condition
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [Can download]}
  contexts:
    web:
      place: web::media-item
- text: The User chooses Begin Downloading and confirms
  kind: actor
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [Title]}
  contexts:
    web:
      place: web::media-item
- text: The Product unskips the media item
  kind: product
  actor: user
  entities:
  - {entity: media, effect: changes, from: Skipped by system, to: Downloading, facts: []}
  contexts:
    web:
      place: web::media-item
- text: The Product refreshes its formats and schedules a download that ignores the Source filters
  kind: product
  actor: user
  entities:
  - {entity: task, effect: creates, to: Scheduled, facts: [Name, Scheduled at, Priority]}
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::media-item
---

# Download media the filters skipped

## Trigger

The User wants a media item the Source filters skipped.

## Outcome

The media item is no longer skipped and its download is scheduled ahead of others, bypassing the Source filters.
