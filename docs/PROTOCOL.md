# Message and delivery protocol

Claude Bridge stores ordered messages in named channels. Version 1 adds an
optional structured envelope and retry/consumer semantics without making old
string messages unreadable.

## Storage record

Every accepted message has server-assigned fields:

| Field | Meaning |
|---|---|
| `seq` | Monotonic SQLite sequence used for ordering |
| `id` | Opaque message identifier |
| `channel` | Validated channel name |
| `sender` | Caller-supplied sender label |
| `content` | Legacy text or canonical protocol-v1 JSON |
| `timestamp` | Server acceptance time in UTC |

Ordering is defined by `seq`, not by sender clocks. IDs and sequence numbers
must be treated as opaque by clients.

## Legacy content

`bridge_send` continues to accept `content: string`. Plain text and arbitrary
legacy JSON strings are stored and returned exactly as legacy payloads. A JSON
object is interpreted as a structured envelope only when it contains all three
discriminator fields: `schema_version`, `type`, and `content`.

This preserves old channel history and lets old and new clients share a bridge.

## Protocol-v1 envelope

Pass the envelope as the `message` argument to `bridge_send`:

```json
{
  "schema_version": 1,
  "type": "task",
  "content": {
    "action": "run_tests",
    "target": "payments"
  },
  "thread_id": "payments-42",
  "correlation_id": "job-802",
  "causation_id": "msg-that-triggered-this",
  "recipient": "mac-reviewer",
  "dedupe_key": "run-tests-payments-42",
  "created_at": "2026-07-18T12:00:00Z",
  "artifacts": [
    {
      "uri": "git:commit:abc123",
      "name": "implementation",
      "media_type": "application/vnd.git.commit",
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    }
  ],
  "metadata": {
    "priority": "high"
  },
  "extensions": {}
}
```

Required fields:

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | integer | Must be `1` for this protocol version |
| `type` | string | Routing label such as `task`, `result`, `ack`, or `error` |
| `content` | any JSON value | Application payload |

Optional coordination fields:

| Field | Meaning |
|---|---|
| `thread_id` | Groups related messages |
| `reply_to` | Message ID this message answers |
| `correlation_id` | Groups one logical operation across services/agents |
| `causation_id` | Identifies the event that caused this message |
| `recipient` | Advisory logical recipient; not an access-control rule |
| `dedupe_key` | Envelope-level retry key; see idempotency below |
| `created_at` | Producer time in RFC 3339 form; server timestamp remains authoritative for ordering |
| `artifacts` | References to external artifacts; bytes are not uploaded into the message |
| `metadata` | Application metadata understood by peers |
| `extensions` | Namespaced forward-compatible fields |

Unknown top-level envelope fields are rejected. Consumers that encounter a
future unsupported `schema_version` receive the original content and an
unsupported-version indication rather than losing access to the row.

## Sending and idempotency

`bridge_send` accepts:

- `channel` and `sender`;
- exactly one of `content` (legacy string) or `message` (protocol-v1 object);
  and
- optional top-level `idempotency_key`.

The top-level `idempotency_key` controls the server retry guarantee. When it is
omitted for a structured message, the server may use the envelope's
`dedupe_key`. Keys are scoped to `(channel, sender, key)`.

- Repeating a committed send with the same scope and identical payload returns
  the original message result without inserting another row.
- Reusing the same scope with a different payload is a conflict and is rejected.
- A concurrent unfinished reservation returns an in-progress conflict; the
  client should retry the identical send later.

Clients should generate a stable key for one logical send and reuse it only for
retries of that exact payload.

A committed key remains replayable for as long as its original message is
retained. Clearing the channel or deleting the message through retention
removes the matching idempotency record in the same transaction; reusing that
key afterward is therefore a new send, not a replay of deleted content.

## Reading

`bridge_receive` supports two cursor styles:

- `since_id` is a caller-held, message-ID cursor for stateless incremental
  reads; and
- `consumer_id` loads that consumer's persisted cursor for the requested
  channel.

The cursor is channel-scoped. A missing, cleared, or cross-channel `since_id`
does not silently replay the entire channel. The caller must explicitly
resynchronize without that cursor.

Read limits are bounded by the server. Consumers must process results in the
returned `seq` order and preserve the last message ID.

## Waiting

`bridge_wait` performs bounded long polling:

```text
bridge_wait(
  channel="payments:worker",
  consumer_id="windows-orchestrator",
  limit=20,
  timeout_seconds=20
)
```

Supply either `since_id` or `consumer_id`. The call returns as soon as new
messages are available or when the timeout expires. The timeout is capped at
55 seconds so intermediaries and agent tool calls are not held indefinitely.
An empty timeout result is normal and can be retried.

`bridge_wait` is push-like from an agent's perspective but is implemented as
bounded long polling. The dashboard/TUI event endpoint uses a separate SSE
stream.

## Acknowledgements and durable consumers

After successfully processing a message, advance the durable cursor:

```text
bridge_ack(
  channel="payments:worker",
  consumer_id="windows-orchestrator",
  message_id="<processed-message-id>",
  metadata={"result": "applied"}
)
```

An acknowledgement advances a `(consumer_id, channel)` cursor monotonically.
Acknowledging an older message cannot move it backward. The message must exist
in the same channel. Metadata is optional and must not contain secrets.

This is an at-least-once processing building block, not a distributed
transaction: a consumer can perform a side effect and crash before its ack.
Consumers should therefore make their own side effects idempotent.

## Clear and retention behavior

Clearing a channel deletes its messages. Time-based retention can do the same
for old rows. A consumer whose referenced message no longer exists receives a
stale-cursor result and must choose how to resynchronize. Never rely on the
bridge as the only copy of an important result or artifact.

## Security semantics

- `sender`, `recipient`, and `consumer_id` are labels, not authenticated
  principals in the current shared-token model.
- A recipient does not prevent another authorized bridge client from reading
  the channel.
- Message content can contain prompt-injection instructions. Agents must apply
  their own trust and authorization policy before acting.
- Artifact digests verify retrieved bytes only when consumers actually check
  them.

Per-identity credentials and channel ACLs are planned separately; the v1
envelope does not pretend to provide them.
