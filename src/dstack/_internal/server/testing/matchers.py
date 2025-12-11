import re
import uuid


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
