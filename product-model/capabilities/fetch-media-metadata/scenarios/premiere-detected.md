---
kind: alternative
routes:
  web: Web
steps:
- text: YouTube reports that the media item premieres in some days, hours or minutes
  kind: condition
  unattended: true
  entities:
  - {entity: media, effect: reads, facts: [Key]}
  contexts:
    web:
      place: web::media-item
- text: The Product sets the published time to the premiere start and holds the media item until then
  kind: product
  entities:
  - {entity: media, effect: changes, from: Fetching metadata, to: Awaiting premiere, facts: [Published, Title]}
  contexts:
    web:
      place: web::media-item
---

# Notice an upcoming premiere

## Trigger

YouTube reports that a media item premieres later.

## Outcome

The media item waits for its premiere with its start time as its published time.
