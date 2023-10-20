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
$ docker exec -i tubesync python3 /app/manage.py dumpdata > some-file.json
```

Then change you database backend over, then use

```bash
$ cat some-file.json | docker exec -i tubesync python3 /app/manage.py loaddata - --format=json
```

As detailed in the Django documentation:

https://docs.djangoproject.com/en/3.1/ref/django-admin/#dumpdata

and:

https://docs.djangoproject.com/en/3.1/ref/django-admin/#loaddata

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
