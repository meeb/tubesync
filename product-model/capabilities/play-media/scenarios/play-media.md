---
kind: primary
routes:
  web: Web
steps:
- text: The media item is downloaded
  kind: condition
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [Download date]}
  contexts:
    web:
      place: web::media-item
- text: The User plays the media in the page
  kind: actor
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [File path]}
  contexts:
    web:
      place: web::media-item
- text: The Product streams the saved file, as audio for an audio-only Source and as video otherwise
  kind: product
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [File path, Container]}
  - {entity: source, effect: reads, facts: [Resolution]}
  contexts:
    web:
      place: web::media-item
---

# Play downloaded media

## Trigger

The User wants to watch or listen to a downloaded media item.

## Outcome

The media plays in the page, as audio for audio-only Sources.
