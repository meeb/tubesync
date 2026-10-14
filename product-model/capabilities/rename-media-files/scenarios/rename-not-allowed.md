---
kind: alternative
routes:
  web: Web
steps:
- text: The deployment renames neither all Sources nor this Source directory
  kind: condition
  unattended: true
  entities:
  - {entity: source, effect: reads, facts: [Directory]}
  contexts:
    web:
      place: web::source
- text: The Product leaves the downloaded files where they are
  kind: product
  entities: []
  contexts:
    web:
      place: web::source
---

# Renaming does not apply

## Trigger

The media of a Source was checked but the deployment renames neither all Sources nor this one.

## Outcome

Downloaded files keep their names.
