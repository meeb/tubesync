---
kind: alternative
routes:
  web: Web
steps:
- text: The User chooses Show skipped media or Only skipped media
  kind: actor
  actor: user
  entities:
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::media
- text: The Product lists skipped media and media with no matching formats, marked manually skipped, skipped by system, disabled at source or no matching formats
  kind: product
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [Title, Can download]}
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::media
---

# Show skipped media

## Trigger

The User wants to see media TubeSync is not downloading.

## Outcome

Skipped media and media without a matching format are listed with the reason.
