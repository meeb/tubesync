---
kind: person
acts: external
references:
- kind: doc
  role: intent
  target: README.md
- kind: code
  role: implementation
  target: tubesync/common/middleware.py#BasicAuthMiddleware
---

# User

The person who runs TubeSync and uses its web interface: adding Sources, watching what is downloaded and keeping media servers informed. When the deployment sets an HTTP username and password, the browser asks for them first.
