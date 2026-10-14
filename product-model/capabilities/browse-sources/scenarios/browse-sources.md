---
kind: primary
routes:
  web: Web
steps:
- text: The User opens the Sources page
  kind: actor
  actor: user
  entities:
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::sources
- text: The Product lists every Source by name with its format summary, media counts and next update target
  kind: product
  actor: user
  entities:
  - {entity: source, effect: reads, facts: [Name, Type, Key, Resolution, Video codec, Audio codec, Prefer 60fps, Prefer HDR, Audio track, Has failed, Delete old media, Days to keep, Target schedule]}
  - {entity: media, effect: reads, facts: []}
  contexts:
    web:
      place: web::sources
- text: The User reads each Source and whether it has permanent failures
  kind: actor
  actor: user
  entities:
  - {entity: source, effect: reads, facts: [Name, Type, Key, Has failed, Target schedule]}
  contexts:
    web:
      place: web::sources
---

# Browse the sources

## Trigger

The User opens the Sources page.

## Outcome

The User sees each Source, ordered by name, with its counts and next update target, and failed Sources flagged.

## Edge cases

- With no Sources the page says none have been added and offers to add one.
