---
kind: primary
routes:
  web: Web
steps:
- text: The User chooses Delete source and confirms without ticking the option to also delete downloaded files
  kind: actor
  actor: user
  entities:
  - {entity: source, effect: reads, facts: [Name, Directory]}
  contexts:
    web:
      place: web::source
- text: The Product stops the Source and marks it as being deleted
  kind: product
  actor: user
  entities:
  - {entity: source, effect: changes, from: Active, to: Deleting, facts: [Name, Download media, Index schedule]}
  contexts:
    web:
      place: web::sources
- text: The Product returns the User to the Sources page with "Your selected source has been deleted."
  kind: product
  actor: user
  entities:
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::sources
- text: The Product removes the media thumbnails and the media, then the Source
  kind: product
  actor: user
  entities:
  - {entity: source, effect: removes, from: Deleting}
  - {entity: media, effect: removes, from: Downloaded, with: source}
  contexts:
    web:
      place: web::sources
---

# Delete a source and keep its files

## Trigger

The User no longer wants a Source synced.

## Outcome

The Source and its media are gone from TubeSync; the downloaded files stay on disk.

## Edge cases

- A media thumbnail is copied next to its file before it is removed, when the file still exists.
