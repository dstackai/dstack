from dstack._internal.core.models.common import EntityReference
from dstack._internal.core.models.profiles import ProfileParams


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
