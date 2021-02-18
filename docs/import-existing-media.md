# TubeSync

## Advanced usage guide - importing existing media

This is a new feature in v0.9 of TubeSync and later. It allows you to mark existing
downloaded media as "downloaded" in TubeSync. You can use this feature if, for example,
you already have an extensive catalogue of downloaded media which you want to mark
as downloaded into TubeSync so TubeSync doesn't re-download media you already have.

## Requirements

Your existing downloaded media MUST contain the unique ID. For YouTube videos, this is
means the YouTube video ID MUST be in the filename.

Supported extensions to be imported are .m4a, .ogg, .mkv, .mp3, .mp4 and .avi. Your
media you want to import must end in one of these file extensions.

## Caveats

As TubeSync does not probe media and your existing media may be re-encoded or in
different formats to what is available in the current media metadata there is no way
for TubeSync to know what codecs, resolution, bitrate etc. your imported media is in.
Any manually imported existing local media will display blank boxes for this
information on the TubeSync interface as it's unavailable.

## Steps

### 1. Add your source to TubeSync

Add your source to TubeSync, such as a YouTube channel. **Make sure you untick the
"download media" checkbox.**

This will allow TubeSync to index all the available media on your source, but won't
start downloading any media.

### 2. Wait

Wait for all the media on your source to be indexed. This may take some time.

### 3. Move your existing media into TubeSync

You now need to move your existing media into TubeSync. You need to move the media
files into the correct download directories created by TubeSync. For example, if you
have downloaded videos for a YouTube channel "TestChannel", you would have added this
as a source called TestChannel and in a directory called test-channel in Tubesync. It
would have a download directory created on disk at:

`/path/to/downloads/test-channel`

You would move all of your pre-existing videos you downloaded outside of TubeSync for
this channel into this directory.

In short, your existing media needs to be moved into the correct TubeSync source
directory to be detected.

This is required so TubeSync can known which Source to link the media to.

### 4. Run the batch import command

Execute the following Django command:

`./manage.py import-existing-media`

When deploying TubeSync inside a container, you can execute this with:

`docker exec -ti tubesync python3 /app/manage.py import-existing-media`

This command will log what its doing to the terminal when you run it.

Internally, `import-existing-media` looks for the unique media key (for YouTube, this
is the YouTube video ID) in the filename and detects the source to link it to based
on the directory the media file is inside.


### 5. Re-enable downloading at the source

Edit your source and re-enable / tick the "download media" option. This will allow
TubeSync to download any missing media you did not manually import.

Note that TubeSync will still get screenshots write `nfo` files etc. for files you
manually import if enabled at the source level.
