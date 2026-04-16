import gpuhunt

from dstack._internal.utils.common import run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def preload_offers_catalog():
    """Pre-load the `gpuhunt` offers catalog so the get offer requests do not pay the catalog download cost."""
    logger.debug("Pre-loading offers catalog")
    catalog = gpuhunt.default_catalog()
    await run_async(catalog.load)
    logger.debug("Pre-loaded offers catalog")
