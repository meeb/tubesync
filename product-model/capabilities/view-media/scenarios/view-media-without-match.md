---
kind: alternative
routes:
  web: Web
steps:
- text: The User opens a media item
  kind: actor
  actor: user
  entities:
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::media-item
- text: No available format matches the Source requirements
  kind: condition
  entities:
  - {entity: media, effect: reads, facts: [Can download]}
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::media-item
- text: The Product warns "Media cannot be downloaded because it has no formats which match the source requirements."
  kind: product
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [Available formats]}
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::media-item
---

# Read media that cannot be downloaded

## Trigger

The User opens a media item for which no format matches its Source.

## Outcome

The page explains that no format matches the Source requirements.

## Edge cases

- Manually skipped media instead says it is marked to be skipped and will not be downloaded.
