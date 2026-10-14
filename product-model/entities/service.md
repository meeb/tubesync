---
references:
- kind: code
  role: implementation
  target: tubesync/sync/views/services.py#S6OverlayReporter
---

# Service

One of the background services running inside the TubeSync container, such as the web server and the task workers.

## Information kept

- **Name** — the service name
- **Running** — whether it is up
- **Ready** — whether it reports ready
- **Process ID** — its process and process group
- **Uptime** — how long it has been up or down
- **Exit code** — how it last stopped
