---
domain: media
relations:
- entity: task
  verb: is worked on by
  cardinality: one-to-many
references:
- kind: code
  role: implementation
  target: tubesync/sync/models/media.py#Media
- kind: code
  role: implementation
  target: tubesync/sync/choices.py#MediaState
- kind: code
  role: implementation
  target: tubesync/sync/templates/sync/media.html
---

# Media

One video or live stream of a Source, from the moment indexing finds it until it is downloaded, skipped or removed.

## Information kept

- **Key** — the YouTube video ID
- **Title** — the video title
- **Description** — the video description
- **Published** — when it was published, or when its premiere starts
- **Duration** — its length
- **Thumbnail** — the thumbnail TubeSync keeps for it
- **Available formats** — the audio, video and combined formats YouTube offers, with resolution, codecs, frame rate and language
- **Matched formats** — the best combined, audio and video formats for its Source, each an exact match or a fallback
- **Can download** — whether a format matches its Source requirements
- **Download date** — when its download completed
- **Downloaded format** — the resolution or format saved
- **Downloaded codecs** — the audio and video codecs saved
- **Container** — the container of the saved file
- **Downloaded FPS** — the frame rate of the saved video
- **Downloaded HDR** — whether the saved video has HDR
- **File size** — the size of the saved file
- **File path** — where the file is saved, following its Source media format

## States

### Fetching metadata

Found by indexing; its details and formats are being fetched.

### Awaiting premiere

A premiere that has not started; held until its published time.

### Downloading

A format matches and no filter skips it; waiting for or in its download.

### No matching formats

No offered format suits its Source; formats are refreshed later.

### Skipped by system

Excluded by its Source filters, or offering no formats.

### Disabled at source

Its Source only indexes and does not download media.

### Manually skipped

Marked never to be downloaded, by the User or because TubeSync removed it.

### Downloaded

Saved to disk.
