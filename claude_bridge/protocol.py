"""Versioned message envelopes with lossless legacy-string compatibility.

Claude Bridge historically stored a message as one opaque string.  That is a
useful compatibility contract and remains the wire/storage representation.
This module adds an opt-in, versioned JSON envelope *inside* that string so
newer clients can coordinate tasks, replies, artifacts, and deduplication
without making older clients unable to read the message.

Use :func:`encode_message_content` before persistence and
:func:`parse_message_content` after reading.  Passing a plain string to the
encoder returns it byte-for-byte unchanged.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, TypeAlias

from .validation import (
    DEFAULT_LIMITS,
    BridgeValidationError,
    ValidationLimits,
    canonical_json,
    validate_idempotency_key,
    validate_json_value,
    validate_message_type,
    validate_raw_content,
    validate_reference,
    validate_sha256,
)


CURRENT_SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = frozenset({CURRENT_SCHEMA_VERSION})

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class ProtocolError(ValueError):
    """Base class for structured-message protocol errors."""


class InvalidEnvelopeError(ProtocolError):
    """Raised when a claimed bridge envelope is malformed."""


class UnsupportedSchemaVersionError(ProtocolError):
    def __init__(self, version: Any) -> None:
        self.version = version
        super().__init__(f"unsupported message schema_version: {version!r}")


def _optional_reference(
    value: Any,
    field_name: str,
    limits: ValidationLimits,
) -> str | None:
    if value is None:
        return None
    return validate_reference(value, field_name, limits)


def _validate_created_at(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise BridgeValidationError(
            "created_at", "invalid_type", "must be an RFC 3339 string"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BridgeValidationError(
            "created_at", "invalid_format", "must be an RFC 3339 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise BridgeValidationError(
            "created_at", "timezone_required", "must include a UTC offset"
        )
    return value


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    """A reference to an artifact; artifact bytes do not travel in messages."""

    uri: str
    name: str | None = None
    media_type: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.uri, str) or not self.uri:
            raise BridgeValidationError("artifacts.uri", "required", "must not be empty")
        if self.uri != self.uri.strip():
            raise BridgeValidationError(
                "artifacts.uri",
                "surrounding_whitespace",
                "must not start or end with whitespace",
            )
        if len(self.uri) > DEFAULT_LIMITS.max_artifact_uri_chars:
            raise BridgeValidationError(
                "artifacts.uri",
                "too_long",
                f"must be at most {DEFAULT_LIMITS.max_artifact_uri_chars} characters",
            )
        if any(ord(char) < 32 or ord(char) == 127 for char in self.uri):
            raise BridgeValidationError(
                "artifacts.uri", "control_character", "must not contain control characters"
            )

        for field_name in ("name", "media_type"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise BridgeValidationError(
                    f"artifacts.{field_name}",
                    "invalid_value",
                    "must be a non-empty string when provided",
                )
        if self.size_bytes is not None:
            if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int):
                raise BridgeValidationError(
                    "artifacts.size_bytes", "invalid_type", "must be an integer"
                )
            if self.size_bytes < 0:
                raise BridgeValidationError(
                    "artifacts.size_bytes", "out_of_range", "must be non-negative"
                )
        if self.sha256 is not None:
            object.__setattr__(
                self, "sha256", validate_sha256(self.sha256, field="artifacts.sha256")
            )
        if not isinstance(self.metadata, Mapping):
            raise BridgeValidationError(
                "artifacts.metadata", "invalid_type", "must be an object"
            )
        metadata = dict(self.metadata)
        validate_json_value(
            metadata,
            field="artifacts.metadata",
            max_bytes=DEFAULT_LIMITS.max_metadata_bytes,
        )
        object.__setattr__(
            self, "metadata", json.loads(canonical_json(metadata, field="artifacts.metadata"))
        )

    def to_dict(self) -> dict[str, JSONValue]:
        result: dict[str, JSONValue] = {"uri": self.uri}
        if self.name is not None:
            result["name"] = self.name
        if self.media_type is not None:
            result["media_type"] = self.media_type
        if self.size_bytes is not None:
            result["size_bytes"] = self.size_bytes
        if self.sha256 is not None:
            result["sha256"] = self.sha256
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ArtifactReference":
        if not isinstance(value, Mapping):
            raise BridgeValidationError(
                "artifacts", "invalid_type", "each artifact must be an object"
            )
        allowed = {"uri", "name", "media_type", "size_bytes", "sha256", "metadata"}
        unknown = set(value) - allowed
        if unknown:
            raise BridgeValidationError(
                "artifacts", "unknown_field", f"unknown field(s): {', '.join(sorted(unknown))}"
            )
        try:
            uri = value["uri"]
        except KeyError as exc:
            raise BridgeValidationError(
                "artifacts.uri", "required", "must be provided"
            ) from exc
        return cls(
            uri=uri,
            name=value.get("name"),
            media_type=value.get("media_type"),
            size_bytes=value.get("size_bytes"),
            sha256=value.get("sha256"),
            metadata=value.get("metadata", {}),
        )


@dataclass(frozen=True, slots=True)
class MessageEnvelope:
    """Schema v1 structured message stored as canonical JSON."""

    content: JSONValue
    type: str = "message"
    schema_version: int = CURRENT_SCHEMA_VERSION
    thread_id: str | None = None
    reply_to: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    recipient: str | None = None
    dedupe_key: str | None = None
    created_at: str | None = None
    artifacts: tuple[ArtifactReference, ...] = ()
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)
    extensions: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise BridgeValidationError(
                "schema_version", "invalid_type", "must be an integer"
            )
        if self.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise UnsupportedSchemaVersionError(self.schema_version)
        object.__setattr__(self, "type", validate_message_type(self.type))
        validate_json_value(self.content, field="content")
        object.__setattr__(
            self, "content", json.loads(canonical_json(self.content, field="content"))
        )

        for field_name in (
            "thread_id",
            "reply_to",
            "correlation_id",
            "causation_id",
            "recipient",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_reference(getattr(self, field_name), field_name, DEFAULT_LIMITS),
            )
        if self.dedupe_key is not None:
            object.__setattr__(
                self, "dedupe_key", validate_idempotency_key(self.dedupe_key)
            )
        object.__setattr__(self, "created_at", _validate_created_at(self.created_at))

        # Bound the count *before* constructing each entry, so a huge list can't
        # run per-item sha256 / canonical-json validation before being rejected.
        if len(self.artifacts) > DEFAULT_LIMITS.max_artifacts:
            raise BridgeValidationError(
                "artifacts",
                "too_many",
                f"must contain at most {DEFAULT_LIMITS.max_artifacts} entries",
            )
        artifacts: list[ArtifactReference] = []
        for artifact in self.artifacts:
            if isinstance(artifact, ArtifactReference):
                artifacts.append(artifact)
            elif isinstance(artifact, Mapping):
                artifacts.append(ArtifactReference.from_dict(artifact))
            else:
                raise BridgeValidationError(
                    "artifacts", "invalid_type", "each artifact must be an object"
                )
        object.__setattr__(self, "artifacts", tuple(artifacts))

        for field_name in ("metadata", "extensions"):
            value = getattr(self, field_name)
            if not isinstance(value, Mapping):
                raise BridgeValidationError(
                    field_name, "invalid_type", "must be an object"
                )
            copied = dict(value)
            validate_json_value(
                copied,
                field=field_name,
                max_bytes=DEFAULT_LIMITS.max_metadata_bytes,
            )
            object.__setattr__(
                self, field_name, json.loads(canonical_json(copied, field=field_name))
            )

        # Enforce the transport budget on the complete envelope, not only its
        # content field.  This includes metadata and artifact references.
        encoded = canonical_json(self.to_dict(), field="message")
        if len(encoded.encode("utf-8")) > DEFAULT_LIMITS.max_message_bytes:
            raise BridgeValidationError(
                "message",
                "too_large",
                f"must encode to at most {DEFAULT_LIMITS.max_message_bytes} UTF-8 bytes",
            )

    def to_dict(self) -> dict[str, JSONValue]:
        result: dict[str, JSONValue] = {
            "schema_version": self.schema_version,
            "type": self.type,
            "content": self.content,
        }
        for field_name in (
            "thread_id",
            "reply_to",
            "correlation_id",
            "causation_id",
            "recipient",
            "dedupe_key",
            "created_at",
        ):
            value = getattr(self, field_name)
            if value is not None:
                result[field_name] = value
        if self.artifacts:
            result["artifacts"] = [artifact.to_dict() for artifact in self.artifacts]
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        if self.extensions:
            result["extensions"] = dict(self.extensions)
        return result

    def to_json(self) -> str:
        return canonical_json(self.to_dict(), field="message")

    def payload_hash(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MessageEnvelope":
        if not isinstance(value, Mapping):
            raise InvalidEnvelopeError("message envelope must be an object")
        allowed = {
            "schema_version",
            "type",
            "content",
            "thread_id",
            "reply_to",
            "correlation_id",
            "causation_id",
            "recipient",
            "dedupe_key",
            "created_at",
            "artifacts",
            "metadata",
            "extensions",
        }
        unknown = set(value) - allowed
        if unknown:
            raise BridgeValidationError(
                "message", "unknown_field", f"unknown field(s): {', '.join(sorted(unknown))}"
            )
        missing = {"schema_version", "type", "content"} - set(value)
        if missing:
            raise BridgeValidationError(
                "message", "required", f"missing field(s): {', '.join(sorted(missing))}"
            )
        artifacts = value.get("artifacts", ())
        if not isinstance(artifacts, (list, tuple)):
            raise BridgeValidationError("artifacts", "invalid_type", "must be an array")
        return cls(
            schema_version=value["schema_version"],
            type=value["type"],
            content=value["content"],
            thread_id=value.get("thread_id"),
            reply_to=value.get("reply_to"),
            correlation_id=value.get("correlation_id"),
            causation_id=value.get("causation_id"),
            recipient=value.get("recipient"),
            dedupe_key=value.get("dedupe_key"),
            created_at=value.get("created_at"),
            artifacts=tuple(artifacts),
            metadata=value.get("metadata", {}),
            extensions=value.get("extensions", {}),
        )


class MessageEncoding(str, Enum):
    LEGACY_TEXT = "legacy_text"
    LEGACY_JSON = "legacy_json"
    STRUCTURED = "structured"
    UNSUPPORTED = "unsupported"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class ParsedMessage:
    """Non-throwing result returned for content read from persistent storage."""

    raw: str
    encoding: MessageEncoding
    envelope: MessageEnvelope | None = None
    schema_version: int | None = None
    error: str | None = None

    @property
    def is_structured(self) -> bool:
        return self.envelope is not None

    @property
    def content(self) -> JSONValue | str:
        return self.envelope.content if self.envelope is not None else self.raw


def _looks_like_envelope(value: Any) -> bool:
    return isinstance(value, dict) and {"schema_version", "type", "content"}.issubset(value)


def parse_message_content(raw: str) -> ParsedMessage:
    """Parse stored content without ever making old/corrupt rows unreadable."""

    if not isinstance(raw, str):
        raise TypeError("stored message content must be a string")
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError, RecursionError):
        return ParsedMessage(raw=raw, encoding=MessageEncoding.LEGACY_TEXT)

    if not _looks_like_envelope(value):
        return ParsedMessage(raw=raw, encoding=MessageEncoding.LEGACY_JSON)

    version = value.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        return ParsedMessage(
            raw=raw,
            encoding=MessageEncoding.INVALID,
            error="schema_version must be an integer",
        )
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        return ParsedMessage(
            raw=raw,
            encoding=MessageEncoding.UNSUPPORTED,
            schema_version=version,
            error=f"unsupported schema_version {version}",
        )
    try:
        envelope = MessageEnvelope.from_dict(value)
    except (
        BridgeValidationError,
        ProtocolError,
        TypeError,
        ValueError,
        RecursionError,
    ) as exc:
        return ParsedMessage(
            raw=raw,
            encoding=MessageEncoding.INVALID,
            schema_version=version,
            error=str(exc),
        )
    return ParsedMessage(
        raw=raw,
        encoding=MessageEncoding.STRUCTURED,
        envelope=envelope,
        schema_version=version,
    )


def decode_message_content(raw: str) -> MessageEnvelope:
    """Strictly decode an envelope, raising for legacy or invalid content."""

    parsed = parse_message_content(raw)
    if parsed.envelope is not None:
        return parsed.envelope
    if parsed.encoding is MessageEncoding.UNSUPPORTED:
        raise UnsupportedSchemaVersionError(parsed.schema_version)
    raise InvalidEnvelopeError(parsed.error or "content is not a structured bridge message")


def encode_message_content(value: str | MessageEnvelope | Mapping[str, Any]) -> str:
    """Encode for the existing TEXT column, preserving raw strings exactly."""

    if isinstance(value, str):
        return validate_raw_content(value)
    if isinstance(value, MessageEnvelope):
        return value.to_json()
    if isinstance(value, Mapping):
        return MessageEnvelope.from_dict(value).to_json()
    raise TypeError("message content must be a string, MessageEnvelope, or mapping")


def compute_payload_hash(value: str | bytes | MessageEnvelope | Mapping[str, Any]) -> str:
    """Return a type-stable digest for idempotency conflict detection."""

    if isinstance(value, bytes):
        payload = b"bytes\x00" + value
    elif isinstance(value, str):
        payload = b"text\x00" + value.encode("utf-8")
    elif isinstance(value, MessageEnvelope):
        payload = b"envelope\x00" + value.to_json().encode("utf-8")
    elif isinstance(value, Mapping):
        payload = b"json\x00" + canonical_json(value).encode("utf-8")
    else:
        raise TypeError("unsupported payload type")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "ArtifactReference",
    "CURRENT_SCHEMA_VERSION",
    "InvalidEnvelopeError",
    "JSONValue",
    "MessageEncoding",
    "MessageEnvelope",
    "ParsedMessage",
    "ProtocolError",
    "SUPPORTED_SCHEMA_VERSIONS",
    "UnsupportedSchemaVersionError",
    "compute_payload_hash",
    "decode_message_content",
    "encode_message_content",
    "parse_message_content",
]
