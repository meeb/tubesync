---
kind: alternative
routes:
  web: Web
steps:
- text: The User ticks the option to also delete downloaded files and confirms
  kind: actor
  actor: user
  entities:
  - {entity: source, effect: reads, facts: [Directory]}
  contexts:
    web:
      place: web::source
- text: The Product marks the Source as being deleted
  kind: product
  actor: user
  entities:
  - {entity: source, effect: changes, from: Active, to: Deleting, facts: [Name, Download media, Index schedule]}
  contexts:
    web:
      place: web::sources
- text: The Product deletes the downloaded files, the media and the Source, then removes the Source directory
  kind: product
  actor: user
  entities:
  - {entity: source, effect: removes, from: Deleting}
  - {entity: media, effect: removes, from: Downloaded, with: source}
  contexts:
    web:
      place: web::sources
---

# Delete a source and its files

## Trigger

The User wants a Source and everything it downloaded gone.

## Outcome

The Source, its media and its whole directory are removed.
