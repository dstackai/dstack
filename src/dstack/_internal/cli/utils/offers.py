import shutil
from collections.abc import Sequence

from rich.table import Table

from dstack._internal.cli.utils.common import console, format_backend, format_instance_availability
from dstack._internal.core.models.instances import InstanceOfferWithAvailability


def print_offers_table(
    offers: Sequence[InstanceOfferWithAvailability],
    total_offers: int,
    max_price: float,
    mute_tail_rows: bool,
):
    table = Table(box=None, expand=shutil.get_terminal_size(fallback=(120, 40)).columns <= 110)
    table.add_column("#")
    table.add_column("BACKEND", style="grey58", ratio=2)
    table.add_column("RESOURCES", ratio=4)
    table.add_column("INSTANCE TYPE", style="grey58", no_wrap=True, ratio=2)
    table.add_column("PRICE", style="grey58", ratio=1)
    table.add_column()

    for i, offer in enumerate(offers, start=1):
        r = offer.instance.resources

        instance = offer.instance.name
        if offer.total_blocks > 1:
            instance += f" ({offer.blocks}/{offer.total_blocks})"
        table.add_row(
            f"{i}",
            format_backend(offer.backend, offer.region),
            r.pretty_format(include_spot=True),
            instance,
            f"${offer.price:.4f}".rstrip("0").rstrip("."),
            format_instance_availability(offer.availability),
            style=None if i == 1 or not mute_tail_rows else "secondary",
        )
    if total_offers > len(offers):
        table.add_row("", "...", style="secondary")

    if len(offers) > 0:
        console.print(table)
        if total_offers > len(offers):
            console.print(
                f"[secondary] Shown {len(offers)} of {total_offers} offers, "
                f"${max_price:3f}".rstrip("0").rstrip(".")
                + "max[/]"
            )
