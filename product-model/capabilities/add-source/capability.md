---
availability:
- {place: web}
domain: sources
references:
- kind: code
  role: implementation
  target: tubesync/sync/views/sources.py#ValidateSourceView
- kind: code
  role: implementation
  target: tubesync/sync/views/sources.py#AddSourceView
- kind: code
  role: implementation
  target: tubesync/sync/views/sources.py#EditSourceMixin
- kind: code
  role: implementation
  target: tubesync/sync/signals.py#source_post_save
- kind: code
  role: implementation
  target: tubesync/sync/choices.py#YouTube_SourceType
- kind: doc
  role: intent
  target: README.md
---

# Add source

The User adds a YouTube channel or playlist as a Source. TubeSync first checks the URL and works out the Source type and key, then the User chooses how the Source is indexed, filtered, downloaded and saved.
