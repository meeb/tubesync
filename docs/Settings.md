Table of contents:

- [`INDEXING_CLEANUP_UNAVAILABLE_POLICY`](#indexing_cleanup_unavailable_policy)
- [`MAX_ENTRIES_PROCESSING`](#max_entries_processing)
- [`MEDIA_FORMATSTR`](#media_formatstr)
- [`SHRINK_NEW_MEDIA_METADATA`](#shrink_new_media_metadata)
- [`SHRINK_OLD_MEDIA_METADATA`](#shrink_old_media_metadata)

--------

### `INDEXING_CLEANUP_UNAVAILABLE_POLICY`

* _Character_: `'processed'` - or `'published'`. Case and surrounding spaces are ignored.
* Decides which media counts as still available when indexing finishes. It only matters for a [`Source`](https://github.com/meeb/tubesync/blob/680913211370154b5de2ce52a8e34f81640ad4d2/tubesync/sync/models/source.py#L28-L33) with _delete removed media_ enabled, because only then is media that is no longer available deleted.
  * `'processed'`: only the media processed during this indexing counts. With [`MAX_ENTRIES_PROCESSING`](#max_entries_processing) set, media beyond the limit is treated as removed, even though it is still published. This is the earlier behaviour.
  * `'published'`: every item the source's index returns counts, including those beyond the limit. Only media that is no longer published is deleted.
* With no processing limit, both values give the same result.

|Added in |
|---------|
| [#1618](../pull/1618) |

--------

### `MAX_ENTRIES_PROCESSING`

* _Integer_: `0` - (zero) Disables the limit entirely. Higher numbers set the limit.
* The maximum number of videos to process while indexing a [`Source`](https://github.com/meeb/tubesync/blob/680913211370154b5de2ce52a8e34f81640ad4d2/tubesync/sync/models/source.py#L28-L33).
* The limit keeps the newest videos. When a source also indexes streams, they share it: streams get half the limit or whatever the videos left unused, whichever is more.
* To stop the limit from deleting media that is still published from a source with _delete removed media_ enabled, set [`INDEXING_CLEANUP_UNAVAILABLE_POLICY`](#indexing_cleanup_unavailable_policy) to `'published'`.

|Added in | Fixed in |
|---------|----------|
| [#305](../pull/305) | [#1044](../pull/1044) |

--------

### `MEDIA_FORMATSTR`

* _Character_: `'{title} - [{key}].{ext}'` - 1-200 quoted characters.
* A customizable default for the [`media_format`](https://github.com/meeb/tubesync/blob/680913211370154b5de2ce52a8e34f81640ad4d2/tubesync/sync/models/source.py#L123-L128) field of new [`Source`](https://github.com/meeb/tubesync/blob/680913211370154b5de2ce52a8e34f81640ad4d2/tubesync/sync/models/source.py#L28-L33) instances.

|Added in | For issue |
|---------|-----------|
| [#1392](../pull/1392) | [#1391](../issues/1391) |

--------

### `SHRINK_NEW_MEDIA_METADATA`

* _Boolean_: `True` - will enable using the filter function.
* Filter out useless data included when metadata is retrieved. This is things such as expired URLs, etc.
* This setting affects newly indexed media only.

|Added in | For issue | Env vars |
|---------|-----------|----------|
| [#612](../pull/612) | [#470](../issues/470) | [#622](../pull/622) |

--------

### `SHRINK_OLD_MEDIA_METADATA`

* _Boolean_: `True` - will enable using the filter function.
* Filter out useless data included when metadata is loaded. This is things such as expired URLs, etc.
* This setting affects metadata on every media instance, the next time it is loaded.

|Added in | For issue | Env vars |
|---------|-----------|----------|
| [#612](../pull/612) | [#470](../issues/470) | [#622](../pull/622) |

--------
