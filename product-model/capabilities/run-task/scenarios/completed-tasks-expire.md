---
kind: alternative
routes:
  web: Web
steps:
- text: A Source indexing starts and completed task records are older than the retention period
  kind: condition
  unattended: true
  entities:
  - {entity: task, effect: reads, facts: [Finished at]}
  - {entity: deployment-settings, effect: reads, facts: [Completed task retention]}
  - {entity: source, effect: reads, facts: []}
  contexts:
    web:
      place: web::completed-tasks
- text: The Product deletes those completed task records
  kind: product
  entities:
  - {entity: task, effect: removes, from: Completed}
  contexts:
    web:
      place: web::completed-tasks
---

# Old completed tasks are forgotten

## Trigger

Indexing of any Source starts.

## Outcome

Completed task records older than the retention period are gone.
