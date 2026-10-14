---
kind: validation
routes:
  web: Web
steps:
- text: The User submits the Source form with a directory that leads outside the downloads directory
  kind: actor
  actor: user
  entities:
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::add-source
- text: The Product refuses the directory, naming the base downloads directory
  kind: product
  actor: user
  entities: []
  contexts:
    web:
      place: web::add-source
---

# Refuse a directory outside the downloads directory

## Trigger

The User gives a Source directory that leads outside the downloads directory.

## Outcome

No Source is created; the directory is refused.
