import logging

from dstack._internal.proxy.gateway.app import make_app


def configure_logging(level: int = logging.INFO):
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    logger = logging.getLogger("dstack")
    logger.setLevel(level)
    logger.addHandler(handler)


configure_logging(logging.DEBUG)
app = make_app()
