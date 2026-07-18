---
name: Bug Report
about: Something isn't working
title: "[BUG] "
labels: bug
assignees: ''
---

**Describe the bug**
A clear description of what's wrong.

**Setup**
- OS (server machine):
- OS (client machine):
- Python version:
- `claude-bridge --version`:
- Client name and exact version:
- Transport: [ ] stdio [ ] Streamable HTTP `/mcp` [ ] legacy `/sse` [ ] REST/event SSE
- Network: [ ] localhost [ ] LAN [ ] tailnet / other VPN [ ] reverse proxy
- Security: [ ] Bearer auth [ ] TLS/HTTPS [ ] `--allow-unauthenticated-network`

**To reproduce**
Steps to reproduce the behavior.

**Expected behavior**
What you expected to happen.

**Logs**
Paste relevant, minimal output from the bridge and client. Remove Bearer tokens,
event-stream query tokens, private message content, IPs you do not want public,
and personal filesystem paths.

**Compatibility classification**
Is this a protocol test, a vendor-client end-to-end run, or an inferred setup?
See `docs/COMPATIBILITY.md` for the project terminology.

> Suspected security vulnerabilities must not be filed here. Use the private
> reporting process in `SECURITY.md`.
