"""Shared validation primitives for Claude Bridge protocol boundaries.

The bridge has several ingress paths (MCP, JSON HTTP, stdio, and future
adapters).  Keeping validation in one dependency-free module prevents those
paths from quietly developing different limits and security behaviour.

The functions in this module validate; they do not silently truncate data.
The one exception is :func:`normalize_limit`, whose documented purpose is to
clamp a pagination hint to a safe range.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ValidationLimits:
    """Limits shared by every public bridge transport.

    Character limits are deliberately separate from byte limits: SQLite and
    Python work with Unicode strings, while request and context budgets are
    ultimately byte-oriented.
    """

    max_channel_chars: int = 256
    max_sender_chars: int = 128
    max_consumer_chars: int = 128
    max_reference_chars: int = 256
    max_idempotency_key_chars: int = 256
    max_message_type_chars: int = 64
    max_message_bytes: int = 128 * 1024
    max_metadata_bytes: int = 16 * 1024
    max_json_depth: int = 16
    max_artifacts: int = 32
    max_artifact_uri_chars: int = 4096


DEFAULT_LIMITS = ValidationLimits()


class BridgeValidationError(ValueError):
    """A safe, structured error suitable for MCP or JSON error responses."""

    def __init__(self, field: str, code: str, message: str) -> None:
        self.field = field
        self.code = code
        self.message = message
        super().__init__(f"{field}: {message}")

    def as_dict(self) -> dict[str, str]:
        return {"field": self.field, "code": self.code, "message": self.message}


_MESSAGE_TYPE_RE = re.compile(r"^[a-z][a-z0-9._-]*$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise BridgeValidationError(field, "invalid_type", "must be a string")
    return value


def _reject_controls(value: str, field: str, *, allow_newlines: bool = False) -> None:
    for char in value:
        if allow_newlines and char in "\n\r\t":
            continue
        if unicodedata.category(char) == "Cc":
            raise BridgeValidationError(
                field, "control_character", "must not contain control characters"
            )


def _validate_identity(value: Any, field: str, max_chars: int) -> str:
    result = _require_string(value, field)
    if not result:
        raise BridgeValidationError(field, "required", "must not be empty")
    if result != result.strip():
        raise BridgeValidationError(
            field, "surrounding_whitespace", "must not start or end with whitespace"
        )
    if len(result) > max_chars:
        raise BridgeValidationError(
            field, "too_long", f"must be at most {max_chars} characters"
        )
    _reject_controls(result, field)
    return result


def validate_channel(value: Any, limits: ValidationLimits = DEFAULT_LIMITS) -> str:
    """Validate a channel while preserving Unicode and ``/`` namespaces."""

    return _validate_identity(value, "channel", limits.max_channel_chars)


def validate_sender(value: Any, limits: ValidationLimits = DEFAULT_LIMITS) -> str:
    return _validate_identity(value, "sender", limits.max_sender_chars)


def validate_consumer(value: Any, limits: ValidationLimits = DEFAULT_LIMITS) -> str:
    return _validate_identity(value, "consumer_id", limits.max_consumer_chars)


def validate_reference(
    value: Any,
    field: str,
    limits: ValidationLimits = DEFAULT_LIMITS,
) -> str:
    """Validate an opaque protocol identifier.

    References are intentionally not restricted to UUIDs so adapters can use
    native IDs from other agent systems.
    """

    return _validate_identity(value, field, limits.max_reference_chars)


def validate_idempotency_key(
    value: Any, limits: ValidationLimits = DEFAULT_LIMITS
) -> str:
    return _validate_identity(
        value, "idempotency_key", limits.max_idempotency_key_chars
    )


def validate_message_type(
    value: Any, limits: ValidationLimits = DEFAULT_LIMITS
) -> str:
    result = _require_string(value, "type")
    if not result:
        raise BridgeValidationError("type", "required", "must not be empty")
    if len(result) > limits.max_message_type_chars:
        raise BridgeValidationError(
            "type",
            "too_long",
            f"must be at most {limits.max_message_type_chars} characters",
        )
    if not _MESSAGE_TYPE_RE.fullmatch(result):
        raise BridgeValidationError(
            "type",
            "invalid_format",
            "must start with a lowercase letter and contain only a-z, 0-9, '.', '_' or '-'",
        )
    return result


def validate_raw_content(
    value: Any, limits: ValidationLimits = DEFAULT_LIMITS
) -> str:
    result = _require_string(value, "content")
    size = len(result.encode("utf-8"))
    if size > limits.max_message_bytes:
        raise BridgeValidationError(
            "content",
            "too_large",
            f"must be at most {limits.max_message_bytes} UTF-8 bytes",
        )
    if "\x00" in result:
        raise BridgeValidationError("content", "nul_byte", "must not contain NUL bytes")
    return result


def _validate_json_tree(
    value: Any,
    *,
    field: str,
    max_depth: int,
    depth: int = 0,
    ancestors: set[int] | None = None,
) -> None:
    if depth > max_depth:
        raise BridgeValidationError(
            field, "too_deep", f"must be nested no more than {max_depth} levels"
        )
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise BridgeValidationError(
                field, "invalid_json", "must contain only finite JSON values"
            )
        return
    if not isinstance(value, (dict, list)):
        raise BridgeValidationError(
            field, "invalid_json", "must contain only JSON objects, arrays, and scalars"
        )

    object_id = id(value)
    parents = set() if ancestors is None else ancestors
    if object_id in parents:
        raise BridgeValidationError(field, "invalid_json", "must not contain cycles")
    parents.add(object_id)
    try:
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise BridgeValidationError(
                        field, "invalid_json", "object keys must be strings"
                    )
                _validate_json_tree(
                    item,
                    field=field,
                    max_depth=max_depth,
                    depth=depth + 1,
                    ancestors=parents,
                )
        else:
            for item in value:
                _validate_json_tree(
                    item,
                    field=field,
                    max_depth=max_depth,
                    depth=depth + 1,
                    ancestors=parents,
                )
    finally:
        parents.remove(object_id)


def _encode_json(value: Any, *, field: str) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise BridgeValidationError(
            field, "invalid_json", "must contain only finite JSON values"
        ) from exc


def canonical_json(value: Any, *, field: str = "value") -> str:
    """Serialize JSON deterministically, rejecting non-JSON Python values."""

    # This general helper has a generous recursion ceiling. Public protocol
    # boundaries apply their tighter ValidationLimits before calling it.
    _validate_json_tree(value, field=field, max_depth=128)
    return _encode_json(value, field=field)


def validate_json_value(
    value: Any,
    *,
    field: str = "content",
    max_bytes: int | None = None,
    limits: ValidationLimits = DEFAULT_LIMITS,
) -> Any:
    """Validate a JSON value without modifying it."""

    _validate_json_tree(
        value, field=field, max_depth=limits.max_json_depth
    )
    encoded = _encode_json(value, field=field)
    budget = limits.max_message_bytes if max_bytes is None else max_bytes
    if len(encoded.encode("utf-8")) > budget:
        raise BridgeValidationError(
            field, "too_large", f"must encode to at most {budget} UTF-8 bytes"
        )
    return value


def validate_sha256(value: Any, *, field: str = "sha256") -> str:
    result = _require_string(value, field).lower()
    if not _HASH_RE.fullmatch(result):
        raise BridgeValidationError(
            field, "invalid_format", "must be a 64-character hexadecimal SHA-256"
        )
    return result


def validate_non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BridgeValidationError(field, "invalid_type", "must be an integer")
    if value < 0:
        raise BridgeValidationError(field, "out_of_range", "must be non-negative")
    return value


def normalize_limit(
    value: Any,
    *,
    default: int = 20,
    minimum: int = 1,
    maximum: int = 500,
    field: str = "limit",
) -> int:
    """Return a safe pagination limit.

    ``None`` selects ``default``. Integer values are clamped; booleans,
    strings, floats, and other accidental coercions are rejected.
    """

    if minimum < 1 or maximum < minimum or not minimum <= default <= maximum:
        raise ValueError("invalid normalize_limit bounds")
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise BridgeValidationError(field, "invalid_type", "must be an integer")
    return max(minimum, min(value, maximum))


def validate_finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BridgeValidationError(field, "invalid_type", "must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise BridgeValidationError(field, "out_of_range", "must be finite")
    return result


__all__ = [
    "BridgeValidationError",
    "DEFAULT_LIMITS",
    "ValidationLimits",
    "canonical_json",
    "normalize_limit",
    "validate_channel",
    "validate_consumer",
    "validate_finite_number",
    "validate_idempotency_key",
    "validate_json_value",
    "validate_message_type",
    "validate_non_negative_int",
    "validate_raw_content",
    "validate_reference",
    "validate_sender",
    "validate_sha256",
]
