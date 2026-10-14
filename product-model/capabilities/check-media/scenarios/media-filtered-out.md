---
kind: alternative
routes:
  web: Web
steps:
- text: A media item has metadata and a matching format
  kind: condition
  unattended: true
  entities:
  - {entity: media, effect: reads, facts: [Title, Duration, Published]}
  contexts:
    web:
      place: web::media-item
- text: The Product applies the Source filters and skips the media item
  kind: product
  entities:
  - {entity: source, effect: reads, facts: [Filter text, Invert filter text, Filter seconds, Filter seconds mode, Download cap, Delete old media, Days to keep]}
  - {entity: media, effect: changes, from: Fetching metadata, to: Skipped by system, facts: [Can download]}
  contexts:
    web:
      place: web::media-item
---

# The source filters skip media

## Trigger

A media item matches a format but the Source filters exclude it.

## Outcome

The media item is skipped by the system and not downloaded.

## Decision points

### Which filter skips it?

What excludes the media item?

- It has no published time → skipped
- It was published before the download cap → skipped
- Its title does not match the filter text, or matches it when the filter is inverted → skipped
- It is shorter than the minimum or longer than the maximum filter seconds → skipped
- It was downloaded longer ago than the days to keep → skipped
