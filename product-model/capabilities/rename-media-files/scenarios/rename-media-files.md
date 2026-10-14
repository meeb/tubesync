---
kind: primary
routes:
  web: Web
steps:
- text: Renaming applies to the Source because all Sources are renamed or its directory is listed for renaming
  kind: condition
  unattended: true
  entities:
  - {entity: source, effect: reads, facts: [Directory, Media format]}
  contexts:
    web:
      place: web::media-item
- text: The Product moves each downloaded file and the files sharing its name to the new path, adopting stray files with the media key
  kind: product
  entities:
  - {entity: media, effect: changes, facts: [File path]}
  contexts:
    web:
      place: web::media-item
- text: The Product rewrites the NFO file when thumbnails are copied and removes emptied folders
  kind: product
  entities:
  - {entity: source, effect: reads, facts: [Write NFO, Copy thumbnails]}
  contexts:
    web:
      place: web::media-item
---

# Rename files to the current media format

## Trigger

The media of a Source was checked and renaming applies to the Source.

## Outcome

Each downloaded file and its companion files carry the name the current media format gives.

## Edge cases

- A file whose new name is already taken is left where it is.
