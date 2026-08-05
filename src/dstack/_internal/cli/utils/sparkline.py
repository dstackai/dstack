from typing import List, Optional, Sequence

from rich.text import Text

SPARKS = "▁▂▃▄▅▆▇"
"""No full block: it fills the cell to the top edge, fusing consecutive rows into one mass."""

NO_DATA = "no data"

Ramp = Sequence[tuple[float, str]]

# Colour encodes scope: device metrics share one ramp, host metrics another, so a job row is
# never mistaken for a device row.
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


def slices(values: Sequence[float], width: int) -> List[tuple[float, float]]:
    """`(peak, mean)` per cell, oldest first -- height is the peak, colour the mean, so a
    card that *touched* 100% reads differently from one that *held* it.

    Cells span the whole series, not its tail. The last cell is the latest sample, so it
    cannot contradict the number printed beside the sparkline.
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
    """Spelled out: next to sparklines a bare `-` reads as a stray glyph."""
    return Text(NO_DATA, style="grey58")


def sparkline(
    values: Optional[Sequence[float]],
    width: int,
    ramp: Optional[Ramp] = None,
    vmax: float = 100.0,
) -> Text:
    """Fixed 0..vmax scale, never autoscaled: height means the same thing on every row."""
    if not values:
        return no_data()
    text = Text()
    for peak, mean in slices(values, width):
        index = int(max(0.0, min(vmax, peak)) / vmax * (len(SPARKS) - 1))
        shade = max(0.0, min(vmax, mean)) / vmax * 100
        text.append(SPARKS[index], style=ramp_style(shade, ramp) if ramp else "cyan")
    return text
