---
appliesTo:
- type: capability
  id: index-source
- type: entity
  id: source
  facts:
  - Index schedule
  - Target schedule
references:
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#schedule_indexing
- kind: code
  role: implementation
  target: tubesync/sync/models/source.py#Source
---

# A source is indexed no more often than its index schedule

Every hour TubeSync schedules indexing for active Sources whose target schedule has come and that were not crawled within their schedule. Schedules of a day or longer run at the target hour, and weekly schedules also on the target weekday; shorter schedules run that long after the last indexing.
