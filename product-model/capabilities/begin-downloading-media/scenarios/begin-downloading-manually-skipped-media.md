---
kind: alternative
routes:
  web: Web
steps:
- text: The media item is manually skipped and a format matches
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
- text: The Product clears the manual skip and schedules the download
  kind: product
  actor: user
  entities:
  - {entity: media, effect: changes, from: Manually skipped, to: Downloading, facts: []}
  - {entity: task, effect: creates, to: Scheduled, facts: [Name, Scheduled at, Priority]}
  contexts:
    web:
      place: web::media-item
---

# Download media that was manually skipped

## Trigger

The User changes their mind about media they skipped, which still has a matching format.

## Outcome

The media item is downloading.
