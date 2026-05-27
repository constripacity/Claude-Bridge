# Claude Bridge

**Real-time cross-machine communication for Claude Code agents.**

![CI](https://github.com/constripacity/claude-bridge/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![MCP](https://img.shields.io/badge/MCP-compatible-orange)

---

Claude Code's native [Agent Teams](https://code.claude.com/docs/en/agent-teams) coordinate multiple instances on the **same machine**. Claude Bridge fills the gap — it lets Claude Code agents on **different machines** communicate in real time over a shared MCP relay server.

```
Windows PC (Claude Code)         MacBook (Claude Code)
         |                                |
         |   SSE · Tailscale / LAN        |  ← server runs here
         +-------> Claude Bridge <--------+
                    :8765
```

One agent sends. The other receives. No polling hacks, no shared filesystems, no cloud dependencies.

---

## Architecture

![Architecture](docs/architecture-v2.png)

---

## Quickstart

### 1. Install (on the machine that will host the server)

```bash
git clone https://github.com/constripacity/claude-bridge.git
cd claude-bridge
pip install -r requirements.txt
```

### 2. Start the server

```bash
python server.py
```

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Claude Bridge — General MCP Relay Server
  http://localhost:8765/             ← Dashboard
  http://localhost:8765/sse          ← Local MCP config
  http://<tailscale-ip>:8765/sse     ← Remote machines
  http://localhost:8765/api/state    ← JSON state for dashboard
  http://localhost:8765/status       ← Health check
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 3. Add to Claude Code MCP config on each machine

**Host machine** — `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "claude-bridge": {
      "type": "sse",
      "url": "http://localhost:8765/sse"
    }
  }
}
```

**Remote machine** — `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "claude-bridge": {
      "type": "sse",
      "url": "http://<HOST_TAILSCALE_IP>:8765/sse"
    }
  }
}
```

That's it. Both Claude Code sessions now have six new tools.

---

## MCP Tools

| Tool | Description |
|------|-------------|
| `bridge_send` | Send a message to a named channel |
| `bridge_receive` | Read messages — pass `since_id` for incremental polling |
| `bridge_channels` | List all active channels and message counts |
| `bridge_ping` | Health check + server stats |
| `bridge_clear` | Clear all messages from a channel |
| `bridge_status` | Cross-channel overview with recent messages |

---

## Usage

Agents communicate over **named channels**. Convention: `<project>:<role>`.

**Machine A (orchestrator):**
```
bridge_send(
  channel="myproject:orchestrator",
  sender="windows",
  content='{"type":"task","phase":1,"action":"run_tests"}'
)
```

**Machine B (worker):**
```
bridge_receive(channel="myproject:orchestrator")
→ gets the task

bridge_send(
  channel="myproject:worker",
  sender="mac",
  content='{"type":"result","phase":1,"status":"complete","tests_run":61,"failures":0}'
)
```

**Machine A polls for results:**
```
bridge_receive(channel="myproject:worker", since_id="<last_id>")
```

The `since_id` parameter ensures each agent only processes new messages on every poll.

---

## Channel Naming

Channels are created on first write — no registration needed.

```
<project>:orchestrator   →  A sends tasks to B
<project>:worker         →  B sends results to A
<project>:events         →  shared event log
<project>:debug          →  verbose diagnostics
general:sync             →  cross-project coordination
```

---

## Recommended Setup: Tailscale

For cross-machine use, [Tailscale](https://tailscale.com) is the simplest and most secure option:

1. Install Tailscale on both machines
2. Both machines join your Tailscale network
3. Use the host machine's Tailscale IP in the remote MCP config
4. Keep port 8765 firewalled to Tailscale only — no public exposure

This works across networks (home, office, travel) without any port forwarding.

---

## Why not use Agent Teams?

Claude Code's built-in Agent Teams (experimental, requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) coordinate agents on the **same machine**. They share a process, a filesystem, and a local network. There's no mechanism for two agents running on separate physical machines to talk to each other.

Claude Bridge is the missing layer. It's intentionally minimal — a relay, not an orchestrator. Your agents stay in control of their own logic.

---

## CLAUDE.md

A ready-to-use `CLAUDE.md` is included. Drop it in your project root or add it to your global `~/.claude/CLAUDE.md` to give every Claude Code session full context on how to use the bridge, which channels belong to which project, and what each machine's role is.

---

## Web Dashboard

Open `http://localhost:8765/` in any browser for a live monitor of channels, messages, and senders. It polls `/api/state` + `/api/messages` every 2 seconds, lets you click into any message for a JSON-highlighted inspector, and includes a working send composer (pick a sender, type or paste JSON, ⌘↵ / Ctrl↵ to send) and a per-channel clear button. Adapts to mobile viewports automatically.

The dashboard speaks a small JSON API alongside the MCP `/sse` transport:

| Endpoint | Purpose |
|----------|---------|
| `GET /api/state` | All channels + counts + senders + uptime in one call |
| `GET /api/messages?channel=X[&since_id=Y][&limit=N]` | Feed for one channel |
| `GET /api/messages/{id}` | Full message detail (parsed JSON, byte size) |
| `POST /api/send` `{channel,sender,content}` | Same effect as `bridge_send` |
| `POST /api/clear` `{channel}` | Drop all messages on a channel |

Sends from the dashboard are indistinguishable from MCP `bridge_send` calls — they share the same INSERT path.

---

## Persistence

Messages are persisted to a local SQLite database (`./claude-bridge.db` by default) so they survive server restarts. Override the path with the `CLAUDE_BRIDGE_DB` environment variable:

```bash
CLAUDE_BRIDGE_DB=/var/lib/claude-bridge/bridge.db python server.py
```

The schema is a single `messages` table — easy to inspect with `sqlite3`. Use `bridge_clear` to drop a channel.

---

## Roadmap

- [x] Optional SQLite persistence (survive server restarts)
- [x] Web dashboard (live channel monitor in the browser)
- [ ] Auth token support (shared secret per channel or global)
- [ ] WebSocket transport (alternative to SSE)
- [ ] `claude-bridge` PyPI package + CLI entrypoint
- [ ] stdio transport (for pure local use without HTTP)
- [ ] Submit to [MCP server directory](https://github.com/modelcontextprotocol/servers)

---

## Requirements

- Python 3.10+
- `mcp`, `starlette`, `uvicorn` (see `requirements.txt`)
- Tailscale (recommended) or shared LAN for cross-machine use

---

## Performance

The server is intentionally lightweight:

- **Idle CPU:** ~0% (M-series efficiency cores, no busy loop)
- **Memory:** ~25MB
- **Latency:** <5ms on LAN, <20ms over Tailscale
- **Messages:** persisted to SQLite (WAL mode) — survives restarts

Safe to run on a MacBook Air M3 without thermal impact.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). PRs welcome, especially for the roadmap items above.

---

## License

MIT — see [LICENSE](LICENSE).
