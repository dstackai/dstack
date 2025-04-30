import logging

from dstack._internal.utils.logging import get_logger


def get_plugin_logger(name: str) -> logging.Logger:
    """
    Use this function to set up loggers in plugins.

    Put at the top of the plugin modules:

    ```
    from dstack.plugins import get_plugin_logger

    logger = get_plugin_logger(__name__)
    ```

    """
    return get_logger(f"dstack.plugins.{name}")
