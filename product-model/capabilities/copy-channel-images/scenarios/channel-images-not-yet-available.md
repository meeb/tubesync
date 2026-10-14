---
kind: edge
routes:
  web: Web
steps:
- text: The Source has no indexed channel data yet
  kind: condition
  unattended: true
  entities:
  - {entity: source, effect: reads, facts: [Last crawl]}
  contexts:
    web:
      place: web::source
- text: The Product postpones copying the channel images and retries later
  kind: product
  entities:
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::source
---

# Channel data is not indexed yet

## Trigger

Channel images are requested before the Source has been indexed.

## Outcome

Copying is retried later with growing delays.
