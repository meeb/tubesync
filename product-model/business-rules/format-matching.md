---
appliesTo:
- type: capability
  id: download-media
- type: capability
  id: check-media
- type: entity
  id: source
  facts:
  - Resolution
  - Video codec
  - Audio codec
  - Prefer 60fps
  - Prefer HDR
  - Audio track
  - Fallback
references:
- kind: code
  role: implementation
  target: tubesync/sync/matching.py#get_best_video_format
- kind: code
  role: implementation
  target: tubesync/sync/matching.py#get_best_audio_format
- kind: code
  role: implementation
  target: tubesync/sync/models/media.py#Media
---

# Media downloads in its source resolution and codecs, or in a fallback the source allows

TubeSync prefers a combined format matching the Source resolution, video codec, audio codec and its 60fps and HDR preferences, then separate video and audio formats it merges. When nothing matches exactly, the Source fallback decides: fail and download nothing, take the next best resolution in any codec, only in the preferred codec, or in any codec but at least HD (500 lines). Fallbacks never go below the smallest video height the deployment allows, 240 lines by default, and AI-upscaled formats are never chosen. Among audio tracks the Source audio track preference wins, then English variants.
