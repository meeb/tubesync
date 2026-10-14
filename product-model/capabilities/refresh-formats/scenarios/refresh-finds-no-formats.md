---
kind: edge
routes:
  web: Web
steps:
- text: YouTube returns no formats for the media item
  kind: condition
  unattended: true
  entities:
  - {entity: media, effect: reads, facts: [Key]}
  contexts:
    web:
      place: web::media-item
- text: The Product schedules another refresh, waiting ten minutes plus one hour for each attempt so far
  kind: product
  entities:
  - {entity: task, effect: changes, from: Failed, to: Scheduled, facts: [Attempts, Scheduled at, Last error]}
  contexts:
    web:
      place: web::tasks
---

# YouTube still offers no formats

## Trigger

Refreshing finds no formats for the media item.

## Outcome

Another refresh is scheduled later, up to fifteen attempts.
