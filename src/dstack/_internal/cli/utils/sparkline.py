"""Sparklines for CLI tables."""

from typing import List, Optional, Sequence

from rich.console import Console
from rich.text import Text

SPARKS = "▁▂▃▄▅▆▇"
"""Stops at 7/8 height on purpose: a full block fills its cell to the top edge, so a column
of them in consecutive rows fuses into one mass and the rows stop reading as separate
series."""

ASCII_SPARKS = "_.:-=+*#%@"
NO_DATA = "no data"

Ramp = Sequence[tuple[float, str]]

# Colour encodes scope. Device metrics share one ramp because GPU utilization and GPU memory
# are two views of the same question; host metrics get a cool one so a job row is never
# mistaken for a device row, and because the economics differ -- a host CPU at 10% is normal,
# not wasted money.
GPU_RAMP: Ramp = ((25, "grey42"), (50, "chartreuse4"), (75, "chartreuse3"), (101, "green1"))
HOST_RAMP: Ramp = (
    (50, "steel_blue3"),
    (90, "deep_sky_blue3"),
    (97, "dark_orange3"),
    (101, "red3"),
)


def ramp_style(value: float, ramp: Ramp) -> str:
    for threshold, style in ramp:
        if value < threshold:
            return style
    return ramp[-1][1]


def supports_unicode(console: Console) -> bool:
    """Whether block glyphs will survive the console's encoding."""
    try:
        SPARKS.encode(console.encoding or "utf-8")
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def slices(values: Sequence[float], width: int) -> List[tuple[float, float]]:
    """`(peak, mean)` per cell, oldest first.

    Two numbers because a cell draws both: glyph height is the peak, colour is the mean.
    Height alone cannot separate a card that *touched* 100% for a few seconds from one that
    *held* it for minutes -- both draw full.

    Cells cover the whole series rather than its tail: metrics arrive about every 10s, so
    taking the last `width` samples would cover a couple of minutes instead of the hour the
    caller asked for. The last cell is the latest sample, since the number printed beside
    the sparkline is that reading and the two must not contradict each other.
    """
    vals = list(values)
    if width < 1:
        return []
    if width == 1 or len(vals) <= width:
        return [(v, v) for v in vals[-width:]]
    history, out = vals[:-1], []
    for i in range(width - 1):
        lo = int(i * len(history) / (width - 1))
        hi = max(lo + 1, int((i + 1) * len(history) / (width - 1)))
        chunk = history[lo:hi]
        out.append((max(chunk), sum(chunk) / len(chunk)))
    out.append((vals[-1], vals[-1]))
    return out


def no_data() -> Text:
    """Spelled out rather than the `-` used elsewhere in the CLI: next to sparklines a bare
    dash reads as a stray character, and "n/a" would be wrong -- the metric applies, it just
    has not arrived yet."""
    return Text(NO_DATA, style="grey58")


def sparkline(
    values: Optional[Sequence[float]],
    width: int,
    ramp: Optional[Ramp] = None,
    vmax: float = 100.0,
    ascii_only: bool = False,
) -> Text:
    """A sparkline on a fixed 0..vmax scale, so glyph height always means the same thing as
    the number beside it and rows stay comparable with each other."""
    if not values:
        return no_data()
    glyphs = ASCII_SPARKS if ascii_only else SPARKS
    text = Text()
    for peak, mean in slices(values, width):
        index = int(max(0.0, min(vmax, peak)) / vmax * (len(glyphs) - 1))
        shade = max(0.0, min(vmax, mean)) / vmax * 100
        text.append(glyphs[index], style=ramp_style(shade, ramp) if ramp else "cyan")
    return text
