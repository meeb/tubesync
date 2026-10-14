---
kind: primary
routes:
  web: Web
steps:
- text: The User opens the dashboard
  kind: actor
  actor: user
  entities: []
  contexts:
    web:
      place: web::dashboard
- text: The Product counts Sources by video and audio, media and downloaded media, and scheduled and completed tasks
  kind: product
  actor: user
  entities:
  - {entity: source, effect: reads, facts: [Resolution]}
  - {entity: media, effect: reads, facts: [Download date]}
  - {entity: task, effect: reads, facts: []}
  contexts:
    web:
      place: web::dashboard
- text: The Product sums downloaded file sizes and lists the ten latest and ten largest downloads
  kind: product
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [Title, Download date, File size, Downloaded format]}
  contexts:
    web:
      place: web::dashboard
- text: The Product shows the run user and group, configuration and downloads directories and database connection
  kind: product
  actor: user
  entities:
  - {entity: deployment-settings, effect: reads, facts: [Run user and group, Config directory, Downloads directory, Database connection]}
  contexts:
    web:
      place: web::dashboard
- text: The User reads the totals and latest downloads
  kind: actor
  actor: user
  entities:
  - {entity: media, effect: reads, facts: [Title, Download date, File size]}
  contexts:
    web:
      place: web::dashboard
---

# Read the dashboard

## Trigger

The User opens TubeSync.

## Outcome

The User sees counts, disk usage, recent and largest downloads and runtime information.
