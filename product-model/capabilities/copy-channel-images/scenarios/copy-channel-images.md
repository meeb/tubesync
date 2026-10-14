---
kind: primary
routes:
  web: Web
steps:
- text: A Source has Copy channel images on and was just added or just turned it on
  kind: condition
  unattended: true
  entities:
  - {entity: source, effect: reads, facts: [Copy channel images, Directory]}
  contexts:
    web:
      place: web::source
- text: The Product finds the channel avatar, banner and thumbnail in the indexed channel data
  kind: product
  entities:
  - {entity: source, effect: reads, facts: [Key]}
  contexts:
    web:
      place: web::source
- text: The Product saves them as poster.jpg, season-poster.jpg, banner.jpg, background.jpg and thumbnail.jpg in the Source directory
  kind: product
  entities:
  - {entity: source, effect: reads, facts: [Directory]}
  contexts:
    web:
      place: web::source
---

# Copy channel images into the source directory

## Trigger

A Source is added with Copy channel images on, or the setting is turned on.

## Outcome

The Source directory holds poster, season poster, banner, background and thumbnail images of the channel.
