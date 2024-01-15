import logging


def configure_logging(level: int = logging.INFO):
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    logger = logging.getLogger("dstack.gateway")
    logger.setLevel(level)
    logger.addHandler(handler)
