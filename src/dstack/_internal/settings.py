import os

from dstack import version

DSTACK_VERSION = os.getenv("DSTACK_VERSION", version.__version__)
DSTACK_RELEASE = os.getenv("DSTACK_RELEASE") is not None or version.__is_release__
DSTACK_USE_LATEST_FROM_BRANCH = os.getenv("DSTACK_USE_LATEST_FROM_BRANCH") is not None


class FeatureFlags:
    """
    dstack feature flags. Feature flags are temporary and can be used when developing
    large features. This class may be empty if there are no such features in
    development. Feature flags are environment variables of the form DSTACK_FF_*
    """
