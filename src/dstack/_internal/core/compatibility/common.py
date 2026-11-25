from typing import Optional, Sequence

from dstack._internal.core.backends.profile_options import AnyBackendProfileOptions
from dstack._internal.core.backends.vastai.profile_options import VastAIProfileOptions
from dstack._internal.core.models.common import IncludeExcludeStrDictType
from dstack._internal.core.models.profiles import ProfileParams


def get_profile_excludes(profile: Optional[ProfileParams]) -> IncludeExcludeStrDictType:
    excludes: IncludeExcludeStrDictType = {}
    if profile is None:
        return excludes
    backend_options_excludes = get_backend_options_excludes(profile.backend_options or [])
    if backend_options_excludes:
        excludes["backend_options"] = backend_options_excludes
    return excludes


def get_backend_options_excludes(
    backend_options: Sequence[AnyBackendProfileOptions],
) -> Optional[IncludeExcludeStrDictType]:
    """
    Returns a `backend_options` exclude mapping that excludes new fields
    when they are unset in all `backend_options`.
    """
    options_excludes: IncludeExcludeStrDictType = {}
    if all(
        not isinstance(opt, VastAIProfileOptions) or opt.min_inet_down is None
        for opt in backend_options
    ):
        options_excludes["min_inet_down"] = True
    if options_excludes:
        return {"__all__": options_excludes}
    return None
