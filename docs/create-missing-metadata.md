# TubeSync

## Advanced usage guide - creating missing metadata

This is a new feature in v0.9 of TubeSync and later. It allows you to create or
re-create missing metadata in your TubeSync download directories for missing `nfo`
files and thumbnails.

If you add a source with "write NFO files" or "copy thumbnails" disabled, download
some media and then update the source to write NFO files or copy thumbnails then
TubeSync will not automatically retroactively attempt to copy or create your missing
metadata files. You can use a special one-off command to manually write missing
metadata files to the correct locations.

## Requirements

You have added a source without metadata writing enabled, downloaded some media, then
updated the source to enable metadata writing.

## Steps

### 1. Run the batch metadata sync command

Execute the following Django command:

`./manage.py sync-missing-metadata`

When deploying TubeSync inside a container, you can execute this with:

`docker exec -ti tubesync python3 /app/manage.py sync-missing-metadata`

This command will log what its doing to the terminal when you run it.

Internally, this command loops over all your sources which have been saved with
"write NFO files" or "copy thumbnails" enabled. Then, loops over all media saved to
that source and confirms that the appropriate thumbnail files have been copied over and
the NFO file has been written if enabled.
