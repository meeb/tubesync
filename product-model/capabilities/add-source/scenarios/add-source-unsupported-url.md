---
kind: validation
routes:
  web: Web
steps:
- text: The User enters a URL that is not a supported YouTube channel or playlist URL
  kind: actor
  actor: user
  entities: []
  contexts:
    web:
      place: web::add-source
- text: The URL matches no supported format
  kind: condition
  entities: []
  contexts:
    web:
      place: web::add-source
- text: The Product refuses the URL with "That URL does not match any supported formats."
  kind: product
  actor: user
  entities: []
  contexts:
    web:
      place: web::add-source
---

# Refuse an unsupported URL

## Trigger

The User enters a URL that is not a YouTube channel or playlist.

## Outcome

No Source is created; the URL is refused as not matching any supported format.
