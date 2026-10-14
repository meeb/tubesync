---
kind: alternative
routes:
  web: Web
steps:
- text: The User changes the directory and saves
  kind: actor
  actor: user
  entities: []
  contexts:
    web:
      place: web::edit-source
- text: The Product moves the existing Source directory to the new location, merging into a directory already there
  kind: product
  actor: user
  entities:
  - {entity: source, effect: changes, facts: [Directory]}
  contexts:
    web:
      place: web::source
---

# Move a source to another directory

## Trigger

The User changes the directory of a Source.

## Outcome

The files already saved for the Source are in the new directory.

## Edge cases

- Entries already present in the target directory are kept; moved entries never replace them.
