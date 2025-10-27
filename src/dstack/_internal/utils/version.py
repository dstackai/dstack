from typing import Optional

import packaging.version


def parse_version(version_string: str) -> Optional[packaging.version.Version]:
    """
    Returns a `packaging.version.Version` instance or `None` if the version is dev/latest.

    Values parsed as the dev/latest version:
    * the "latest" literal
    * any "0.0.0" release, e.g., "0.0.0", "0.0.0a1", "0.0.0.dev0"
    """
    if version_string == "latest":
        return None
    try:
        version = packaging.version.parse(version_string)
    except packaging.version.InvalidVersion as e:
        raise ValueError(f"Invalid version: {version_string}") from e
    if version.release == (0, 0, 0):
        return None
    return version
