---
availability:
- {place: web}
domain: sources
references:
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#download_source_images
- kind: code
  role: implementation
  target: tubesync/sync/signals.py#source_pre_save
---

# Copy channel images

When a Source copies channel images, TubeSync saves the channel avatar, banner and thumbnail into the Source directory under the names media servers look for.
