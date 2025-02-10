import asyncio
import logging
import sys

from pythonjsonlogger.json import JsonFormatter

from dstack._internal.cli.utils.common import console
from dstack._internal.cli.utils.rich import DstackRichHandler
from dstack._internal.server import settings


class AsyncioCancelledErrorFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not record.exc_info:
            return True
        if isinstance(record.exc_info[1], asyncio.CancelledError):
            return False
        return True


def configure_logging():
    formatters = {
        "rich": logging.Formatter(fmt="%(message)s", datefmt="[%X]"),
        "standard": logging.Formatter(
            fmt="%(levelname)s %(asctime)s.%(msecs)03d %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        ),
        "json": JsonFormatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s",
            json_ensure_ascii=False,
            rename_fields={"name": "logger", "asctime": "timestamp", "levelname": "level"},
        ),
    }
    handlers = {
        "rich": DstackRichHandler(console=console),
        "standard": logging.StreamHandler(stream=sys.stdout),
        "json": logging.StreamHandler(stream=sys.stdout),
    }
    if settings.LOG_FORMAT not in formatters:
        raise ValueError(f"Invalid settings.LOG_FORMAT: {settings.LOG_FORMAT}")
    formatter = formatters.get(settings.LOG_FORMAT)
    handler = handlers.get(settings.LOG_FORMAT)
    handler.setFormatter(formatter)
    handler.addFilter(AsyncioCancelledErrorFilter())
    root_logger = logging.getLogger(None)
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.ROOT_LOG_LEVEL)
    dstack_logger = logging.getLogger("dstack")
    dstack_logger.setLevel(settings.LOG_LEVEL)
    # paramiko emits error logs in cases handled by dstack
    logging.getLogger("paramiko").setLevel(logging.CRITICAL)
