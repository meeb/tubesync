# TubeSync

## Advanced usage guide - reset media metadata from the command line

This command allows you to reset all media item metadata. You might want to use
this if you have a lot of media items with invalid metadata and you want to
wipe it which triggers the metadata to be redownloaded.


## Requirements

You have added some sources and media

## Steps

### 1. Run the reset tasks command

Execute the following Django command:

`./manage.py reset-metadata`

When deploying TubeSync inside a container, you can execute this with:

`docker exec -ti tubesync python3 /app/manage.py reset-metadata`

This command will log what its doing to the terminal when you run it.

When this is run, new tasks will be immediately created so all your media
items will start downloading updated metadata straight away, any missing information
such as thumbnails will be redownloaded, etc.
