import argparse

from dstack._internal.cli.services.args import cpu_spec, disk_spec, gpu_spec, memory_spec
from dstack._internal.cli.services.configurators.base import ArgsParser
from dstack._internal.core.models import resources
from dstack._internal.core.models.configurations import AnyRunConfiguration


def register_resources_args(parser: ArgsParser) -> None:
    parser.add_argument(
        "--cpu",
        type=cpu_spec,
        help=(
            "Request CPU for the run."
            " The format is [code]ARCH[/]:[code]COUNT[/] (all parts are optional)"
        ),
        dest="cpu_spec",
        metavar="SPEC",
    )
    parser.add_argument(
        "--gpu",
        type=gpu_spec,
        help=(
            "Request GPU for the run."
            " The format is [code]NAME[/]:[code]COUNT[/]:[code]MEMORY[/] (all parts are optional)"
        ),
        dest="gpu_spec",
        metavar="SPEC",
    )
    parser.add_argument(
        "--memory",
        type=memory_spec,
        help="Request the size range of RAM for the run. Example [code]--memory 128GB..256GB[/]",
        dest="memory_spec",
        metavar="RANGE",
    )
    parser.add_argument(
        "--disk",
        type=disk_spec,
        help="Request the size range of disk for the run. Example [code]--disk 100GB..[/]",
        dest="disk_spec",
        metavar="RANGE",
    )


def apply_resources_args(args: argparse.Namespace, conf: AnyRunConfiguration) -> None:
    if args.cpu_spec:
        conf.resources.cpu = resources.CPUSpec.parse_obj(args.cpu_spec)
    if args.gpu_spec:
        conf.resources.gpu = resources.GPUSpec.parse_obj(args.gpu_spec)
    if args.memory_spec:
        conf.resources.memory = args.memory_spec
    if args.disk_spec:
        conf.resources.disk = args.disk_spec
