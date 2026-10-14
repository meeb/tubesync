---
availability:
- {place: web}
domain: media
references:
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#download_media_file
- kind: code
  role: implementation
  target: tubesync/sync/models/media.py#Media
- kind: code
  role: implementation
  target: tubesync/sync/models/media__tasks.py#download_finished
- kind: code
  role: implementation
  target: tubesync/sync/youtube.py#download_media
- kind: code
  role: implementation
  target: tubesync/sync/matching.py#get_best_combined_format
- kind: doc
  role: intent
  target: README.md
---

# Download media

TubeSync downloads a media item in the best format matching its Source, applying the Source options for SponsorBlock, subtitles, embedded metadata and thumbnails, then saves its companion files and tells media servers.
