---
kind: primary
routes:
  web: Web
steps:
- text: The User opens the Services page
  kind: actor
  actor: user
  entities:
  - {entity: service, effect: reads, facts: []}
  contexts:
    web:
      place: web::services
- text: The Product lists each service with whether it is running and ready, its process and uptime
  kind: product
  actor: user
  entities:
  - {entity: service, effect: reads, facts: [Name, Running, Ready, Process ID, Uptime, Exit code]}
  contexts:
    web:
      place: web::services
- text: The User reads which services are running
  kind: actor
  actor: user
  entities:
  - {entity: service, effect: reads, facts: [Name, Running]}
  contexts:
    web:
      place: web::services
---

# Read service status

## Trigger

The User wants to know whether the TubeSync workers are up.

## Outcome

The User sees each service, how many are running, and their process and uptime.

## Edge cases

- Outside the container image no services are listed.
