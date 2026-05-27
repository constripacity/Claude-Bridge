# Claude Bridge — Master Agent Prompt

This file is the shared CLAUDE.md for any Claude Code session that uses the
Claude Bridge MCP server. Place it in the project root or reference it from
your global `~/.claude/CLAUDE.md`.

---

## What is Claude Bridge

Claude Bridge is a lightweight MCP relay server running on one machine (the
**host**) at `localhost:8765` locally, or `<host-address>:8765` from any
other machine on the same Tailscale network or LAN.

It gives every Claude Code instance a set of tools to send and receive messages
over named channels in real time. Channels are project-scoped and created on
first write.

This is the primary coordination layer for multi-machine work.

---

## Your Identity

At the start of every session, identify yourself before using the bridge:

- **On Windows:** your sender ID is `windows`
- **On macOS:** your sender ID is `mac`
- **On Linux:** your sender ID is `linux`
- **On another machine:** use a short, descriptive ID, e.g. `vps-01`, `watcher`

Always include your sender ID in every `bridge_send` call. Never guess — check
your machine if unsure.

---

## Available Bridge Tools

| Tool | When to use |
|------|-------------|
| `bridge_ping` | Always run this first to confirm the bridge is online |
| `bridge_send` | Send a message, result, task, or event to a channel |
| `bridge_receive` | Poll a channel for new messages since your last check |
| `bridge_channels` | Inspect what channels are active in this session |
| `bridge_status` | Get a full cross-channel overview — useful at session start |
| `bridge_clear` | Reset a channel when starting a fresh task phase |

---

## Channel Convention

All channels follow the pattern: `<project>:<role>`

### Standard channels per project

| Channel | Direction | Purpose |
|---------|-----------|---------|
| `<project>:orchestrator` | Orchestrator → Worker | Tasks, instructions, phase triggers |
| `<project>:worker` | Worker → Orchestrator | Results, outputs, completion signals |
| `<project>:events` | Both | Shared event log, milestones, errors |
| `<project>:debug` | Both | Verbose output, diagnostics |

### Cross-project channels

| Channel | Purpose |
|---------|---------|
| `general:sync` | Ad-hoc coordination not tied to a specific project |
| `general:status` | High-level status updates across all active projects |

Create new channels freely. There is no registration step — write to a channel
and it exists.

---

## Communication Protocol

### Polling

There is no push notification. Poll `bridge_receive` every **3–5 seconds**
when waiting for a response from another agent. Use `since_id` on every call
after the first to avoid reprocessing messages.

```
Step 1:  result = bridge_receive(channel="myproject:orchestrator")
         → note the id of the last message as <last_id>

Step 2:  result = bridge_receive(channel="myproject:orchestrator", since_id="<last_id>")
         → only returns messages newer than <last_id>
```

### Message format

Messages can be plain text or JSON. Use JSON for structured data:

```json
{
  "type": "task",
  "phase": 1,
  "action": "scan_artifacts",
  "params": { "target": "/Applications" }
}
```

```json
{
  "type": "result",
  "phase": 1,
  "status": "complete",
  "count": 14,
  "artifacts": ["com.apple.finder", "com.apple.security.plist"]
}
```

Always include a `type` field so the receiving agent can route the message
without parsing the full content.

### Acknowledgement

When you receive a task message, send an acknowledgement before starting work:

```
bridge_send(channel="myproject:worker", sender="mac", content='{"type":"ack","phase":1,"status":"starting"}')
```

This lets the orchestrator know the task was received and work has begun.

---

## Session Startup Checklist

Run this at the start of every bridged Claude Code session:

1. `bridge_ping` — confirm server is online
2. `bridge_status` — see what's already in the channels from previous turns
3. Identify your role (orchestrator or worker) for this session
4. Clear stale channels if starting a new phase: `bridge_clear`
5. Announce your presence: `bridge_send(channel="general:status", sender="<id>", content="<id> online — starting <project> session")`

If the host bridge runs with `CLAUDE_BRIDGE_AUTH_TOKEN` (or `--auth-token`)
set, your `claude mcp add` for this machine needs the matching
`--header "Authorization: Bearer <token>"`; without it `bridge_ping` will
fail and every tool call returns an auth error.

---

## Role Definitions

These are conventions, not constraints — pick whichever machine plays each role
for your workflow.

### Orchestrator

The orchestrator holds the long-term project context (memory, notes, repo
history). Its job is to:

- Break work into phases and send tasks via `<project>:orchestrator`
- Monitor `<project>:worker` for results
- Update memory and project notes with completed outputs
- Make decisions about next steps based on worker results
- Never do platform-specific work that belongs on the worker

### Worker + Bridge Host

The worker runs the Bridge server and executes platform-specific tasks. Its
job is to:

- Keep the bridge server running before any session starts
- Poll `<project>:orchestrator` for incoming tasks
- Execute the task (file ops, API calls, builds, tests, etc.)
- Send structured results back via `<project>:worker`
- Never hold long-term memory — rely on the orchestrator for context

---

## Error Handling

If the bridge is unreachable:
- Host: check that the bridge is running (`claude-bridge` or `python -m claude_bridge`)
- Remote: verify the host is reachable on the chosen network path (LAN, Tailscale, etc.) and use `bridge_ping` to test

If a message is malformed or missing fields, send an error result:
```json
{ "type": "error", "message": "Missing required field: target", "phase": 1 }
```

If a task takes longer than expected, send a progress heartbeat every 30s:
```json
{ "type": "heartbeat", "phase": 1, "progress": "ran 28 of 70 tests, 0 failures so far" }
```

---

## Active Projects Using the Bridge

Update this section as projects are onboarded:

| Project | Channels | Orchestrator | Worker |
|---------|----------|-------------|--------|
| *(add your projects here)* | | | |

---

## Notes

- Messages are persisted to SQLite (`./claude-bridge.db` by default) and survive
  server restarts. Long-term project memory should still live in your notes /
  repo — the bridge is a transport, not an archive.
- Keep `bridge_status` calls cheap — use `since_id` on `bridge_receive` rather
  than re-reading full channel history on every poll.
- The bridge is project-agnostic. This CLAUDE.md is the only place that gives
  it project context.
