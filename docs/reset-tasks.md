# TubeSync

## Advanced usage guide - reset tasks from the command line

This is a new feature in v1.0 of TubeSync and later. It allows you to reset all
scheduled tasks from the command line as well as the "reset tasks" button in the
"tasks" tab of the dashboard.

This is useful for TubeSync installations where you may have a lot of media and
sources added and the "reset tasks" button may take too long to the extent where
the page times out (with a 502 error or similar issue).

## Requirements

You have added some sources and media

## Steps

### 1. Run the reset tasks command

Execute the following Django command:

`./manage.py reset-tasks`

When deploying TubeSync inside a container, you can execute this with:

`docker exec -ti tubesync python3 /app/manage.py reset-tasks`

This command will log what its doing to the terminal when you run it.

When this is run, new tasks will be immediately created so all your sources will be
indexed again straight away, any missing information such as thumbnails will be
redownloaded, etc.
