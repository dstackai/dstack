import re
from typing import Dict, Optional

# dstack resource tags allow alphanumeric tags with some special symbols in values.
# Should be valid across most backends (e.g. AWS).
# Does not guarantee that they are valid across all backends (e.g. GCP).
# So backends need to filter bad tags out.
TAG_KEY_PATTERN = re.compile(r"^[_\-a-zA-Z0-9]{1,60}$")
TAG_VALUE_PATTERN = re.compile(r"^[a-zA-Z0-9 .:/=_\-+@]{0,256}$")


def tags_validator(tags: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
    if tags is None:
        return
    validate_tags(tags)
    return tags


def validate_tags(tags: Dict[str, str]):
    for k, v in tags.items():
        _validate_tag(k, v)


def _validate_tag(key: str, value: str):
    if not is_valid_tag_key(key):
        raise ValueError(
            f"Invalid tag key {key}. The key must match regex '{TAG_KEY_PATTERN.pattern}'"
        )
    if not is_valid_tag_value(value):
        raise ValueError(
            f"Invalid tag value {value}. The value must match regex '{TAG_VALUE_PATTERN.pattern}'"
        )


def is_valid_tag_key(name: str) -> bool:
    match = re.match(TAG_KEY_PATTERN, name)
    return match is not None


def is_valid_tag_value(value: str) -> bool:
    match = re.match(TAG_VALUE_PATTERN, value)
    return match is not None
