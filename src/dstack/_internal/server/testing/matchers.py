import re
import uuid

from dstack._internal.core.backends.base.compute import is_valid_provider_ref


class SomeUUID4Str:
    """
    A matcher that compares equal to any valid UUID4 string
    """

    # Simplified UUID regex: just checks the 8-4-4-4-12 hex structure
    _uuid_regex = re.compile(
        r"^[0-9a-f]{8}-"
        r"[0-9a-f]{4}-"
        r"[0-9a-f]{4}-"
        r"[0-9a-f]{4}-"
        r"[0-9a-f]{12}$"
    )

    def __eq__(self, other):
        if isinstance(other, str):
            if not self._uuid_regex.match(other):
                return False
            try:
                return uuid.UUID(other).version == 4
            except ValueError:
                return False

        return False

    def __repr__(self):
        return "SomeUUID4Str()"


class SomeProviderRef:
    """
    A matcher that compares equal to any valid `provider_ref`
    """

    def __eq__(self, other):
        return isinstance(other, str) and is_valid_provider_ref(other)

    def __repr__(self):
        return "SomeProviderRef()"
