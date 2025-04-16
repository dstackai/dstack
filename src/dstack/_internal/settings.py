import os

from dstack import version

DSTACK_VERSION = os.getenv("DSTACK_VERSION", version.__version__)
if DSTACK_VERSION == "0.0.0":
    # The build backend (hatching) requires not None for versions,
    # but the code currently treats None as dev version.
    # TODO: update the code to treat 0.0.0 as dev version.
    DSTACK_VERSION = None
DSTACK_RELEASE = os.getenv("DSTACK_RELEASE") is not None or version.__is_release__
DSTACK_USE_LATEST_FROM_BRANCH = os.getenv("DSTACK_USE_LATEST_FROM_BRANCH") is not None


class FeatureFlags:
    """
    dstack feature flags. Feature flags are temporary and can be used when developing
    large features. This class may be empty if there are no such features in
    development. Feature flags are environment variables of the form DSTACK_FF_*
    """
