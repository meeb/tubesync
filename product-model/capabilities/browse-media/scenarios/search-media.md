---
kind: alternative
routes:
  web: Web
steps:
- text: The User enters text and optionally ticks "In description?"
  kind: actor
  actor: user
  entities: []
  contexts:
    web:
      place: web::media
- text: The Product lists media whose key or title, or description when ticked, contains the text
  kind: product
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [Key, Title, Description]}
  contexts:
    web:
      place: web::media
---

# Search media

## Trigger

The User looks for particular media.

## Outcome

Media whose key or title contains the text, or its description when asked, is listed.
