---
domain: sources
relations:
- entity: media
  verb: has
  cardinality: one-to-many
- entity: task
  verb: is worked on by
  cardinality: one-to-many
references:
- kind: code
  role: implementation
  target: tubesync/sync/models/source.py#Source
- kind: code
  role: implementation
  target: tubesync/sync/choices.py
---

# Source

A YouTube channel or playlist TubeSync keeps in sync: how often it is indexed, which of its media is downloaded in which format, and how the files are named and kept.

## Information kept

- **Type** — YouTube channel, YouTube channel by ID, or YouTube playlist
- **Key** — the channel name, channel ID or playlist ID on YouTube
- **Name** — a friendly name used only inside TubeSync
- **Directory** — the folder, inside the downloads directory, its media is saved into
- **Filter text** — a regular expression media titles are matched against
- **Invert filter text** — whether titles matching the filter text are skipped instead of kept
- **Filter seconds** — a duration limit in seconds; empty or 0 means no duration filter
- **Filter seconds mode** — whether the duration limit is a minimum or a maximum length
- **Media format** — the file name pattern for saved media, built from variables such as date, title and key
- **Target schedule** — the date and time indexing aims for; its hour, and weekday for weekly schedules, fix when long schedules run
- **Index schedule** — how often it is indexed, from every hour to every 7 days, or Never
- **Index videos** — whether its videos are indexed
- **Index streams** — whether its live streams are indexed (channels only)
- **Download media** — whether its media is downloaded or only indexed
- **Download cap** — media published longer ago than this is not downloaded (no cap, or one week to ten years)
- **Delete old media** — whether media is deleted after the days to keep
- **Days to keep** — how many days after download media is kept when deleting old media
- **Resolution** — the desired resolution, from 360p to 4320p, or audio only
- **Video codec** — the preferred video codec: AV1, VP9 or AVC1 (H.264)
- **Audio codec** — the preferred audio codec: OPUS or MP4A
- **Prefer 60fps** — whether 60 frames per second is preferred where available
- **Prefer HDR** — whether HDR is preferred where available
- **Audio track** — whether the original recorded language or the publisher default audio track is downloaded
- **Fallback** — what to do when the resolution and codecs are not available: fail, or take the next best resolution with any codec, only the preferred codec, or any codec but at least HD
- **Delete removed media** — whether media no longer listed on the channel or playlist is removed
- **Delete files on disk** — whether files are deleted when their media is removed from TubeSync
- **Copy channel images** — whether the channel banner and avatar are saved into its directory
- **Copy thumbnails** — whether thumbnails are saved beside the media files
- **Write NFO** — whether an NFO file with the media information is written beside each file
- **Write JSON** — whether a JSON file with the media information is written beside each file
- **Embed metadata** — whether metadata is embedded into each file
- **Embed thumbnail** — whether the thumbnail is embedded into each file
- **SponsorBlock** — whether SponsorBlock is used
- **SponsorBlock categories** — which SponsorBlock categories are removed from downloaded videos
- **Write subtitles** — whether subtitles are downloaded
- **Auto-generated subtitles** — whether auto-generated subtitles are accepted
- **Subtitle languages** — a comma-separated list of subtitle languages, such as en,fr or all,-fr
- **Created** — when it was added to TubeSync
- **Last crawl** — when it was last indexed successfully
- **Has failed** — whether its last indexing found no media at all

## States

### Active

Indexed on its schedule, with its media checked and downloaded by its settings.

### Deleting

Stopped and named "[Deleting]" while its media and the Source itself are removed.
