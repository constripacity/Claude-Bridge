"""Shared boundary-validation tests."""

import json
import time

import pytest

from claude_bridge.validation import (
    BridgeValidationError,
    GENERAL_JSON_MAX_DEPTH,
    ValidationLimits,
    loads_bounded_json,
    normalize_limit,
    validate_channel,
    validate_json_value,
    validate_raw_content,
    validate_sender,
)


def test_unicode_and_namespaced_channels_are_supported():
    assert validate_channel("projekt/über:review") == "projekt/über:review"


@pytest.mark.parametrize("value", ["", " leading", "trailing ", "bad\nchannel", 5])
def test_invalid_channel_is_rejected(value):
    with pytest.raises(BridgeValidationError):
        validate_channel(value)


def test_sender_and_content_have_independent_limits():
    limits = ValidationLimits(max_sender_chars=4, max_message_bytes=5)
    assert validate_sender("four", limits) == "four"
    with pytest.raises(BridgeValidationError) as exc_info:
        validate_sender("fives", limits)
    assert exc_info.value.code == "too_long"
    assert exc_info.value.as_dict()["field"] == "sender"

    # UTF-8 bytes, not code points: each emoji occupies four bytes.
    assert validate_raw_content("🛰", limits) == "🛰"
    with pytest.raises(BridgeValidationError, match="UTF-8 bytes"):
        validate_raw_content("🛰🛰", limits)


def test_json_depth_and_size_are_bounded():
    limits = ValidationLimits(max_json_depth=2)
    validate_json_value({"a": [1]}, limits=limits)
    with pytest.raises(BridgeValidationError) as exc_info:
        validate_json_value({"a": [[1]]}, limits=limits)
    assert exc_info.value.code == "too_deep"


def test_bounded_json_depth_does_not_depend_on_the_python_version():
    at_limit = "[" * GENERAL_JSON_MAX_DEPTH + "]" * GENERAL_JSON_MAX_DEPTH
    assert loads_bounded_json(at_limit) == json.loads(at_limit)
    with pytest.raises(ValueError, match="nested more than"):
        loads_bounded_json("[" + at_limit + "]")


def test_bounded_json_ignores_brackets_inside_strings():
    raw = json.dumps({"text": "[{\"" * GENERAL_JSON_MAX_DEPTH, "tail": "a\\"})
    assert loads_bounded_json(raw) == json.loads(raw)


def test_bounded_json_scans_an_unterminated_string_in_linear_time():
    raw = '"' + '\\"' * 64_000
    started = time.perf_counter()
    with pytest.raises(ValueError):
        loads_bounded_json(raw)
    assert time.perf_counter() - started < 1


def test_json_validation_rejects_cycles_non_string_keys_and_python_tuples():
    cyclic = []
    cyclic.append(cyclic)
    with pytest.raises(BridgeValidationError, match="cycles"):
        validate_json_value(cyclic)
    with pytest.raises(BridgeValidationError, match="keys must be strings"):
        validate_json_value({1: "value"})
    with pytest.raises(BridgeValidationError, match="JSON objects"):
        validate_json_value((1, 2))


def test_pagination_limit_clamps_without_accepting_coercions():
    assert normalize_limit(None, default=20, maximum=100) == 20
    assert normalize_limit(-1, maximum=100) == 1
    assert normalize_limit(999, maximum=100) == 100
    with pytest.raises(BridgeValidationError):
        normalize_limit("10")
    with pytest.raises(BridgeValidationError):
        normalize_limit(True)
