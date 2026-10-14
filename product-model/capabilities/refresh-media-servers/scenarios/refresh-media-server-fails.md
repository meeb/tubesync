---
kind: edge
routes:
  web: Web
steps:
- text: A media server answers a library refresh with an unexpected status
  kind: condition
  unattended: true
  entities:
  - {entity: media-server, effect: reads, facts: [Host, Libraries]}
  contexts:
    web:
      place: web::tasks
- text: The Product fails the refresh task with an error asking to check the media server details
  kind: product
  entities:
  - {entity: task, effect: changes, from: Running, to: Failed, facts: [Last error]}
  - {entity: media-server, effect: reads, facts: []}
  contexts:
    web:
      place: web::tasks
---

# A media server refuses the refresh

## Trigger

A media server answers a library refresh with an error.

## Outcome

The refresh task records the failure for the User to see among tasks.
