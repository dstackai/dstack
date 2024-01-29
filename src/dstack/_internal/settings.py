import os

from dstack import version

DSTACK_VERSION = os.getenv("DSTACK_VERSION", version.__version__)
DSTACK_RELEASE = os.getenv("DSTACK_RELEASE") is not None or version.__is_release__
