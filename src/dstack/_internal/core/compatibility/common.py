from typing import Optional

from dstack._internal.core.models.common import EntityReference, IncludeExcludeSetType
from dstack._internal.core.models.profiles import ProfileParams


def get_profile_excludes(profile: Optional[ProfileParams]) -> IncludeExcludeSetType:
    excludes: IncludeExcludeSetType = set()
    if profile is None:
        return excludes
    if profile.backend_options is None:
        excludes.add("backend_options")
    return excludes


def patch_profile_params(params: ProfileParams) -> None:
    # If there are no project-prefixed fleets, replace all EntityReference with str
    # for compatibility with pre-0.20.14 servers that don't support EntityReference.
    if params.fleets is not None and all(
        EntityReference.parse(f).project is None for f in params.fleets
    ):
        params.fleets = [
            fleet_ref.format() if isinstance(fleet_ref, EntityReference) else fleet_ref
            for fleet_ref in params.fleets
        ]
