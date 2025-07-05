# TubeSync

## Advanced usage guide - using other database backends

This is a new feature in v1.0 of TubeSync and later. It allows you to use a custom
existing external database server instead of the default SQLite database. You may want
to use this if you encounter performance issues with adding very large or a large
number of channels and database write contention (as shown by errors in the log)
become an issue.

## Requirements

TubeSync supports SQLite (the automatic default) as well as PostgreSQL, MySQL and
MariaDB. For MariaDB just follow the MySQL instructions as the driver is the same.

You should start with a blank install of TubeSync. Migrating to a new database will
reset your database. If you are comfortable with Django you can export and re-import
existing database data with:

```bash
# Stop services
$ docker exec -t tubesync \
    bash -c 'for svc in \
    /run/service/{gunicorn,huey-*,tubesync*-worker} ; \
do \
    /command/s6-svc -wd -D "${svc}" ; \
done'
# Backup the database into a compressed file
$ docker exec -t tubesync \
    python3 /app/manage.py \
    dumpdata --format jsonl \
    --exclude background_task \
    --output /downloads/tubesync-database-backup.jsonl.xz
```

Writing the compressed backup file to your `/downloads/` makes sense, as long as that directory is still available after destroying the current container.
If you have a configuration where that file will be deleted, choose a different place to store the output (perhaps `/config/`, if it has sufficient storage available) and place the file there instead.

You can also copy the file from the container to the local filesystem (`/tmp/` in this example) with:

```bash
$ docker cp \
    tubesync:/downloads/tubesync-database-backup.jsonl.xz \
    /tmp/
```

If you use `-` as the destination, then `docker cp` provides a `tar` archive.

After you have changed your database backend over, then use:

```bash
# Stop services
$ docker exec -t tubesync \
    bash -c 'for svc in \
    /run/service/{gunicorn,huey-*,tubesync*-worker} ; \
do \
    /command/s6-svc -wd -D "${svc}" ; \
done'
# Load fixture file into the database
$ docker exec -t tubesync \
    python3 /app/manage.py \
    loaddata /downloads/tubesync-database-backup.jsonl.xz
```

Or, if you only have the copy in `/tmp/`, then you would use:
```bash
# Stop services
$ docker exec -t tubesync \
    bash -c 'for svc in \
    /run/service/{gunicorn,huey-*,tubesync*-worker} ; \
do \
    /command/s6-svc -wd -D "${svc}" ; \
done'
# Load fixture data from standard input into the database
$ xzcat /tmp/tubesync-database-backup.jsonl.xz | \
    docker exec -i tubesync \
    python3 /app/manage.py \
    loaddata --format=jsonl -
```

As detailed in the Django documentation:

* https://docs.djangoproject.com/en/5.2/ref/django-admin/#dumpdata

and:

* https://docs.djangoproject.com/en/5.2/ref/django-admin/#loaddata

Further instructions are beyond the scope of TubeSync documenation and you should refer
to Django documentation for more details.

If you are not comfortable with the above, then skip the `dumpdata` steps, however
remember you will start again with a completely new database.

## Steps

### 1. Create a database in your external database server

You need to create a database and a user with permissions to access the database in
your chosen external database server. Steps vary between PostgreSQL, MySQL and MariaDB
so this is up to you to work out.

### 2. Set the database connection string environment variable

You need to provide the database connection details to TubeSync via an environment
variable. The environment variable name is `DATABASE_CONNECTION` and the format is the
standard URL-style string. Examples are:

`postgresql://tubesync:password@localhost:5432/tubesync`

and

`mysql://tubesync:password@localhost:3306/tubesync`

*Important note:* For MySQL databases make SURE you create the tubesync database with
`utf8mb4` encoding, like:

`CREATE DATABASE tubesync CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;`

Without `utf8mb4` encoding things like emojis in video titles (or any extended UTF8
characters) can cause issues.

### 3. Start TubeSync and check the logs

Once you start TubeSync with the new database connection you should see the folling log
entry in the container or stdout logs:

`2021-04-04 22:42:17,912 [tubesync/INFO] Using database connection: django.db.backends.postgresql://tubesync:[hidden]@localhost:5432/tubesync`

If you see a line similar to the above and the web interface loads, congratulations,
you are now using an external database server for your TubeSync data!

## Database Compression (For MariaDB)
With a lot of media files the `sync_media` table grows in size quickly.
You can save space using column compression using the following steps while using MariaDB:

 1. Stop tubesync 
 2. Execute `ALTER TABLE sync_media MODIFY metadata LONGTEXT COMPRESSED;` on database tubesync
 3. Start tunesync and confirm the connection still works.

## Docker Compose

If you're using Docker Compose and simply want to connect to another container with
the DB for the performance benefits, a configuration like this would be enough:

```
 tubesync-db:
  image: postgres:17
  container_name: tubesync-db
  restart: unless-stopped
  volumes:
   - /<path/to>/tubesync-db:/var/lib/postgresql/data
  environment:
   - POSTGRES_DB=tubesync
   - POSTGRES_USER=postgres
   - POSTGRES_PASSWORD=testpassword

 tubesync:
  image: ghcr.io/meeb/tubesync:latest
  container_name: tubesync
  restart: unless-stopped
  ports:
   - 4848:4848
  volumes:
   - /<path/to>/tubesync/config:/config
   - /<path/to>/YouTube:/downloads
  environment:
   - DATABASE_CONNECTION=postgresql://postgres:testpassword@tubesync-db:5432/tubesync
  depends_on:
   - tubesync-db
```
