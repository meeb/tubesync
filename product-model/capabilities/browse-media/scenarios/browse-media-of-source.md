---
kind: alternative
routes:
  web: Web
steps:
- text: The User chooses to view the items linked to this Source
  kind: actor
  actor: user
  entities:
  - {entity: source, effect: reads, facts: [Name]}
  contexts:
    web:
      place: web::source
- text: The Product lists only that Source media and notes the filter
  kind: product
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [Title, Thumbnail, Download date]}
  - {entity: source, effect: reads, facts: [Name]}
  contexts:
    web:
      place: web::media
---

# Browse the media of one source

## Trigger

The User chooses View media on a Source page.

## Outcome

Only that Source media is listed, with a note naming the Source.
