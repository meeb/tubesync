---
availability:
- {place: web}
domain: sources
references:
- kind: code
  role: implementation
  target: tubesync/sync/views/sources.py#SourceView
- kind: code
  role: implementation
  target: tubesync/sync/templates/sync/source.html
---

# View source

The User reads a Source: its YouTube URL, where it saves, every setting, an example file name, when it last crawled and is next due, and the errors its tasks have hit.
