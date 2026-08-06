from typing import Optional

from dstack._internal.core.models.common import IncludeExcludeSetType
from dstack._internal.core.models.profiles import ProfileParams


def get_profile_excludes(profile: Optional[ProfileParams]) -> IncludeExcludeSetType:
    excludes: IncludeExcludeSetType = set()
    if profile is None:
        return excludes
    return excludes
