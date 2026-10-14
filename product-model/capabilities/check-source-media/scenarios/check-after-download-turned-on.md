---
kind: primary
routes:
  web: Web
steps:
- text: A Source was saved and its media check is due
  kind: condition
  unattended: true
  entities:
  - {entity: source, effect: reads, facts: [Download media]}
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::source
- text: The Product re-checks every media item of the Source against its current settings
  kind: product
  entities:
  - {entity: media, effect: changes, from: Disabled at source, to: Downloading, facts: [Can download]}
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::media
- text: The Product refreshes the formats of media that has none matching and schedules the renaming of downloaded files
  kind: product
  entities:
  - {entity: task, effect: creates, to: Scheduled, facts: [Name, Scheduled at]}
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::media
---

# Media follows a source that starts downloading

## Trigger

The User turns Download media on for a Source that only indexed.

## Outcome

Media that was disabled at source and matches is scheduled to download.

## Edge cases

- The check waits while the Source is being indexed.
