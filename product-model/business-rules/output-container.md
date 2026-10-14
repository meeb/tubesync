---
appliesTo:
- type: capability
  id: download-media
- type: entity
  id: source
  facts:
  - Resolution
  - Audio codec
references:
- kind: code
  role: implementation
  target: tubesync/sync/models/source.py#Source
---

# Audio-only sources save m4a or ogg files and video sources save mkv files

The container follows from the Source: audio-only Sources save MP4A audio as m4a and OPUS audio as ogg, and every video Source saves Matroska (mkv) files, so that no invalid codec and container pair can be chosen.
