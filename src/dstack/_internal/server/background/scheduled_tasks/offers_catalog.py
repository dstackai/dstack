import gpuhunt

from dstack._internal.utils.common import run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def preload_offers_catalog():
    """Pre-load the `gpuhunt` offers catalog so the get offer requests do not pay the catalog download cost."""
    logger.debug("Pre-loading offers catalog")
    # The first `default_catalog()` call downloads and parses the catalog, so it must not run
    # on the event loop. Later calls return the cached catalog, which `load()` refreshes.
    catalog = await run_async(gpuhunt.default_catalog)
    await run_async(catalog.load)
    logger.debug("Pre-loaded offers catalog")
