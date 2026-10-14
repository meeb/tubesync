---
domain: media-servers
references:
- kind: code
  role: implementation
  target: tubesync/sync/models/media_server.py#MediaServer
- kind: code
  role: implementation
  target: tubesync/sync/mediaservers.py
---

# Media server

A Plex or Jellyfin server on the network that TubeSync asks to refresh its libraries.

## Information kept

- **Type** — Plex or Jellyfin
- **Host** — host name or IP address
- **Port** — port number, 1 to 65535
- **Use HTTPS** — whether TubeSync connects over HTTPS
- **Verify HTTPS** — whether the HTTPS certificate must be valid
- **Token** — the Plex token or Jellyfin API key TubeSync uses
- **Libraries** — the comma-separated library IDs to refresh
