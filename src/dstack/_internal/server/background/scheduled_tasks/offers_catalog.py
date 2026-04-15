import gpuhunt

from dstack._internal.utils.common import run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def preload_offers_catalog():
    """Pre-load the `gpuhunt` offers catalog so the first offer request doesn't pay the S3 download cost."""
    logger.debug("Pre-loading `gpuhunt` offers catalog")
    await run_async(gpuhunt.default_catalog)
    logger.debug("`gpuhunt` offers catalog pre-loaded")
