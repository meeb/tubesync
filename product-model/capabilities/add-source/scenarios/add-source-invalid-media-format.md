---
kind: validation
routes:
  web: Web
steps:
- text: The User submits the Source form with a file name format that uses unknown variables
  kind: actor
  actor: user
  entities:
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::add-source
- text: The media format cannot produce an example file name
  kind: condition
  entities:
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::add-source
- text: The Product refuses the form and points the User to the table of valid media format variables
  kind: product
  actor: user
  entities:
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::add-source
---

# Refuse an invalid media format

## Trigger

The User adds a Source whose media format cannot produce a file name.

## Outcome

No Source is created and the media format field shows the error.
