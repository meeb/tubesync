---
kind: primary
routes:
  web: Web
steps:
- text: A Source is active and its target schedule has come, with no crawl since its last scheduled run
  kind: condition
  unattended: true
  entities:
  - {entity: source, effect: reads, facts: [Index schedule, Target schedule, Last crawl, Index videos, Index streams, Download media]}
  contexts:
    web:
      place: web::source
- text: The Product asks YouTube for the videos of the Source, and its live streams when indexed, within the download cap
  kind: product
  entities:
  - {entity: source, effect: reads, facts: [Key, Type, Download cap]}
  contexts:
    web:
      place: web::source
- text: The Product records the crawl time and clears any earlier failure
  kind: product
  entities:
  - {entity: source, effect: changes, facts: [Last crawl, Has failed]}
  contexts:
    web:
      place: web::source
- text: The Product creates a media item for each video it has not seen before
  kind: product
  entities:
  - {entity: media, effect: creates, to: Fetching metadata, facts: [Key, Title, Duration, Published]}
  contexts:
    web:
      place: web::media
- text: The Product schedules metadata and thumbnail downloads for each new media item, then a check of all media of the Source
  kind: product
  entities:
  - {entity: task, effect: creates, to: Scheduled, facts: [Name, Scheduled at]}
  - {entity: source, effect: reads, facts: []}
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::media
---

# Index a source and find new media

## Trigger

A Source is due for indexing on its schedule, or the User asked to sync it now.

## Outcome

New videos of the Source are media items waiting for metadata, and the Source records its last crawl.

## Edge cases

- A Source whose index schedule is Never, or that indexes neither videos nor streams, is not indexed.
- Media of a Source that downloads media gets its metadata fetched ahead of media of Sources that only index.
