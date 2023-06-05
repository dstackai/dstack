import logging
import os
import sys


def configure_root_logger():
    logger = logging.getLogger(None)
    handler = logging.StreamHandler(stream=sys.stdout)
    formatter = logging.Formatter(
        fmt="%(levelname)s %(asctime)s.%(msecs)03d %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(os.getenv("DSTACK_HUB_ROOT_LOG_LEVEL", "ERROR").upper())


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(os.getenv("DSTACK_HUB_LOG_LEVEL", "ERROR").upper())
    return logger
