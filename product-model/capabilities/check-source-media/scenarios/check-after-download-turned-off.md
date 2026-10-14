---
kind: alternative
routes:
  web: Web
steps:
- text: A Source with Download media off was saved
  kind: condition
  unattended: true
  entities:
  - {entity: source, effect: reads, facts: [Download media]}
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::source
- text: The Product re-checks the media of the Source and stops queueing their downloads
  kind: product
  entities:
  - {entity: media, effect: changes, from: Downloading, to: Disabled at source, facts: []}
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::media
---

# Media follows a source that stops downloading

## Trigger

The User turns Download media off for a Source.

## Outcome

Media waiting to download is listed as disabled at source instead.

## Edge cases

- A download already running is not interrupted.
