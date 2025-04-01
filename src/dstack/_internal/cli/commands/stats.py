import argparse

from dstack._internal.cli.commands.metrics import MetricsCommand
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class StatsCommand(MetricsCommand):
    NAME = "stats"

    def _command(self, args: argparse.Namespace):
        logger.warning("`dstack stats` is deprecated in favor of `dstack metrics`")
        super()._command(args)
