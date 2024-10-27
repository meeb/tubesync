# TubeSync

## Advanced usage guide - update media paths from the command line

This command allows you to all media paths. You might want to use
this if you have renamed the Media Format for a source especially 
if the folders are changed.


## Requirements

You have added some sources and media

## Steps

### 1. Run the update media paths command

Execute the following Django command:

`./manage.py update-media-paths`

When deploying TubeSync inside a container, you can execute this with:

`docker exec -ti tubesync python3 /app/manage.py update-media-paths`

There are options for this command:
* --source
  * Only target a single source
  * Use: `./manage.py update-media-paths --source=source_name_here`
* --no-rename
  * Do not rename files, only move them to another directory
  * No value
  * Use: `./manage.py update-media-paths --no-rename`
* --dryrun
  * Make no changes, only print out
  * No value
  * Use:  `./manage.py update-media-paths --dryrun`

This command will log what its doing to the terminal when you run it.
Highly recommended to do a dryrun and reading the log to understand what will be changed.