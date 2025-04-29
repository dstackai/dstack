import logging

from dstack._internal.utils.logging import get_logger


def get_plugin_logger(name: str) -> logging.Logger:
    return get_logger(f"dstack.plugins.{name}")
