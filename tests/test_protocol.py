"""Versioned message protocol and legacy compatibility tests."""

import json

import pytest

from claude_bridge.protocol import (
    ArtifactReference,
    InvalidEnvelopeError,
    MessageEncoding,
    MessageEnvelope,
    UnsupportedSchemaVersionError,
    compute_payload_hash,
    decode_message_content,
    encode_message_content,
    parse_message_content,
)
from claude_bridge.validation import BridgeValidationError


def test_plain_text_round_trips_byte_for_byte():
    raw = "  legacy text\nwith unicode: Grüße 🛰️  "
    assert encode_message_content(raw) == raw
    parsed = parse_message_content(raw)
    assert parsed.encoding is MessageEncoding.LEGACY_TEXT
    assert parsed.raw == raw
    assert parsed.content == raw
    assert not parsed.is_structured


def test_legacy_json_is_not_misclassified_as_envelope():
    raw = '{"type":"task","phase":1}'
    parsed = parse_message_content(raw)
    assert parsed.encoding is MessageEncoding.LEGACY_JSON
    assert parsed.raw == raw
    assert parsed.envelope is None


def test_structured_envelope_round_trip_with_coordination_fields():
    artifact = ArtifactReference(
        uri="https://example.test/build.zip",
        name="build.zip",
        media_type="application/zip",
        size_bytes=42,
        sha256="AB" * 32,
        metadata={"platform": "windows"},
    )
    envelope = MessageEnvelope(
        type="task.result",
        content={"summary": "Tests passed", "count": 105},
        thread_id="thread-12",
        reply_to="msg-11",
        correlation_id="job-3",
        causation_id="msg-10",
        recipient="reviewer",
        dedupe_key="build-2026-07-18",
        created_at="2026-07-18T04:00:00Z",
        artifacts=(artifact,),
        metadata={"priority": 2},
        extensions={"com.example/review": {"required": True}},
    )

    encoded = encode_message_content(envelope)
    # Canonical output is deterministic and starts with the alphabetically
    # first key rather than relying on construction order.
    assert encoded == envelope.to_json()
    assert encode_message_content(envelope) == encoded

    parsed = parse_message_content(encoded)
    assert parsed.encoding is MessageEncoding.STRUCTURED
    assert parsed.envelope == envelope
    assert parsed.content == {"summary": "Tests passed", "count": 105}
    assert parsed.envelope.artifacts[0].sha256 == "ab" * 32
    assert json.loads(encoded)["schema_version"] == 1


def test_mapping_can_be_encoded_directly():
    value = {"schema_version": 1, "type": "message", "content": "hello"}
    encoded = encode_message_content(value)
    assert decode_message_content(encoded).content == "hello"


def test_unsupported_version_is_losslessly_reported():
    raw = '{"schema_version":2,"type":"message","content":"future"}'
    parsed = parse_message_content(raw)
    assert parsed.encoding is MessageEncoding.UNSUPPORTED
    assert parsed.schema_version == 2
    assert parsed.raw == raw
    with pytest.raises(UnsupportedSchemaVersionError):
        decode_message_content(raw)


def test_malformed_claimed_envelope_does_not_break_history_reads():
    raw = '{"schema_version":1,"type":"NOT VALID","content":"x"}'
    parsed = parse_message_content(raw)
    assert parsed.encoding is MessageEncoding.INVALID
    assert parsed.raw == raw
    assert "lowercase" in parsed.error
    with pytest.raises(InvalidEnvelopeError):
        decode_message_content(raw)


def test_unknown_v1_fields_are_rejected_instead_of_silently_ignored():
    raw = (
        '{"schema_version":1,"type":"message","content":"x",'
        '"corelation_id":"typo"}'
    )
    parsed = parse_message_content(raw)
    assert parsed.encoding is MessageEncoding.INVALID
    assert "corelation_id" in parsed.error


def test_envelope_rejects_non_finite_and_oversized_content():
    with pytest.raises(BridgeValidationError, match="finite JSON"):
        MessageEnvelope(content={"value": float("nan")})
    with pytest.raises(BridgeValidationError, match="at most"):
        MessageEnvelope(content="x" * (128 * 1024))


def test_artifact_validation_rejects_bad_integrity_hash():
    with pytest.raises(BridgeValidationError, match="SHA-256"):
        ArtifactReference(uri="bridge://artifact/1", sha256="not-a-hash")


def test_payload_digest_is_deterministic_and_type_stable():
    a = MessageEnvelope(type="task", content={"b": 2, "a": 1})
    b = MessageEnvelope(type="task", content={"a": 1, "b": 2})
    assert compute_payload_hash(a) == compute_payload_hash(b)
    assert compute_payload_hash("{\"a\":1}") != compute_payload_hash({"a": 1})
    assert compute_payload_hash(b"x") != compute_payload_hash("x")
