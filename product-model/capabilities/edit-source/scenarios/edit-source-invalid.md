---
kind: validation
routes:
  web: Web
steps:
- text: The User saves the Source form with an invalid file name format or directory
  kind: actor
  actor: user
  entities:
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::edit-source
- text: The Product refuses the form and keeps the Source as it was
  kind: product
  actor: user
  entities:
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::edit-source
---

# Refuse invalid source settings

## Trigger

The User saves a Source with an invalid media format or a directory outside the downloads directory.

## Outcome

The Source is unchanged and the form shows the error.
