import re
from typing import Dict

from dstack._internal.core.errors import ComputeError


def validate_tags(tags: Dict[str, str]):
    for k, v in tags.items():
        if not _is_valid_tag(k, v):
            raise ComputeError(
                "Invalid Azure resource tags. "
                "See tags restrictions: https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/tag-resources#limitations"
            )


def _is_valid_tag(key: str, value: str) -> bool:
    return _is_valid_tag_key(key) and _is_valid_tag_value(value)


TAG_KEY_PATTERN = re.compile(r"^(?!.*[<>&\\%?\/]).{1,512}$")
TAG_VALUE_PATTERN = re.compile(r".{0,256}$")


def _is_valid_tag_key(key: str) -> bool:
    return TAG_KEY_PATTERN.match(key) is not None


def _is_valid_tag_value(value: str) -> bool:
    return TAG_VALUE_PATTERN.match(value) is not None
