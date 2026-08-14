"""Secret redaction for everything copied out of the agent workspace."""

import os
from typing import Any, Sequence

_REDACTION = "[redacted]"
_REDACTION_BYTES = _REDACTION.encode("utf-8")
# Replacing shorter values such as "1" or "false" corrupts unrelated diagnostics.
_MIN_REDACTED_SUBSTRING_LENGTH = 8
_SENSITIVE_INHERITED_ENV_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)


def get_redacted_values(values: Sequence[str]) -> tuple[str, ...]:
    """Longest-first, so redacting a shorter secret can't leave the tail of a
    longer secret that contains it exposed."""
    return tuple(sorted({value for value in values if value}, key=len, reverse=True))


def contains_redacted_value(value: Any, redacted_values: Sequence[str]) -> bool:
    if isinstance(value, str):
        return any(
            value == redacted
            or (len(redacted) >= _MIN_REDACTED_SUBSTRING_LENGTH and redacted in value)
            for redacted in redacted_values
        )
    if isinstance(value, dict):
        return any(contains_redacted_value(item, redacted_values) for item in value.values())
    if isinstance(value, list):
        return any(contains_redacted_value(item, redacted_values) for item in value)
    return False


def get_sensitive_inherited_env_values() -> list[str]:
    return [value for name in _SENSITIVE_INHERITED_ENV_NAMES if (value := os.getenv(name))]


def redact(value: str, redacted_values: Sequence[str]) -> str:
    for redacted_value in redacted_values:
        if value == redacted_value:
            return _REDACTION
        if len(redacted_value) >= _MIN_REDACTED_SUBSTRING_LENGTH:
            value = value.replace(redacted_value, _REDACTION)
    return value


def redact_bytes(value: bytes, redacted_values: Sequence[str]) -> bytes:
    """Redacts in raw bytes to preserve the file's exact newlines and any
    non-UTF-8 bytes."""
    for redacted_value in redacted_values:
        # Environment values decode with surrogateescape, so encoding them back
        # the same way is what returns their original bytes.
        encoded = redacted_value.encode("utf-8", errors="surrogateescape")
        if value == encoded:
            return _REDACTION_BYTES
        if len(redacted_value) >= _MIN_REDACTED_SUBSTRING_LENGTH:
            value = value.replace(encoded, _REDACTION_BYTES)
    return value


def redact_structure(value: Any, redacted_values: Sequence[str]) -> Any:
    if isinstance(value, str):
        return redact(value, redacted_values)
    if isinstance(value, list):
        return [redact_structure(item, redacted_values) for item in value]
    if isinstance(value, dict):
        return {
            redact(key, redacted_values): redact_structure(item, redacted_values)
            for key, item in value.items()
        }
    return value
