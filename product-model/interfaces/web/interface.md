---
type: web
actors:
- user
entryPoints:
- web: /
references:
- kind: code
  role: implementation
  target: tubesync/tubesync/urls.py
- kind: code
  role: implementation
  target: tubesync/sync/urls.py
- kind: code
  role: implementation
  target: tubesync/common/templates/base.html
- kind: doc
  role: intent
  target: README.md
---

# Web interface

The browser interface every part of TubeSync is administered through, on port 4848 of the container by default: the dashboard, Sources, Media, Services, Tasks and Media Servers pages. When the deployment sets an HTTP username and password, every page asks for them.
