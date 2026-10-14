---
singleton: true
references:
- kind: code
  role: implementation
  target: tubesync/tubesync/settings.py
- kind: code
  role: implementation
  target: tubesync/tubesync/local_settings.py.container
- kind: doc
  role: intent
  target: README.md
---

# Deployment settings

The settings of one TubeSync installation, given as environment variables when the container starts rather than in the web interface.

## Information kept

- **HTTP authentication** — the username and password the browser must give, when both are set
- **Rename all sources** — whether downloaded files of every Source are renamed to the current media format; on by default
- **Rename sources** — the Source directories whose files are renamed when not all are
- **Upgrade media** — whether downloaded videos are downloaded again when a format with more lines appears; on by default
- **Smallest video height** — the smallest video height a fallback may download; 240 pixels by default
- **Directory prefix** — whether Source directories sit under video and audio folders; on by default
- **Completed task retention** — how many days completed task records are kept; 7 by default
- **Run user and group** — the user and group IDs TubeSync runs and writes files as
- **Config directory** — where the database, thumbnails and cache are kept
- **Downloads directory** — where Sources save their media
- **Database connection** — the SQLite file or external database TubeSync uses
