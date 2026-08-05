from dstack._internal.cli.utils.sparkline import (
    GPU_RAMP,
    HOST_RAMP,
    NO_DATA,
    SPARKS,
    ramp_style,
    slices,
    sparkline,
)


class TestSlices:
    def test_cells_cover_the_whole_series_not_its_tail(self):
        """Samples arrive ~10s apart, so taking the last `width` of them would cover a
        couple of minutes instead of the hour the caller asked for."""
        cells = slices(list(range(1000)), 10)
        assert len(cells) == 10
        assert cells[0][0] < 200  # first cell is early history, not a recent sample

    def test_last_cell_is_the_latest_sample(self):
        """The number printed beside the sparkline is that reading; if the last cell were
        its slice's peak instead, a value that just dropped would draw tall next to a
        label reading 0."""
        assert slices([79.0] * 997 + [0.0, 0.0, 0.0], 10)[-1] == (0.0, 0.0)

    def test_height_is_the_peak_and_colour_is_the_mean(self):
        peak, mean = slices([0.0] * 17 + [100.0, 0.0], 2)[0]
        assert peak == 100.0
        assert mean < 10.0

    def test_shorter_than_width_is_returned_as_is(self):
        assert slices([1, 2, 3], 10) == [(1, 1), (2, 2), (3, 3)]


class TestSparkline:
    def test_width_and_fixed_scale(self):
        assert sparkline([0] * 60, 10, GPU_RAMP).plain == SPARKS[0] * 10
        assert sparkline([100] * 60, 10, GPU_RAMP).plain == SPARKS[-1] * 10

    def test_never_fills_the_cell_to_the_top(self):
        assert "█" not in SPARKS
        assert "█" not in sparkline([100] * 60, 10, GPU_RAMP).plain

    def test_height_means_fraction_of_capacity_not_of_the_window(self):
        """Fitting the axis to the window would draw 154GB of 800GB as a full bar."""
        climbing = [(10 + i * 0.145) / 800 * 100 for i in range(1000)]
        assert sparkline(climbing, 10, GPU_RAMP).plain[-1] in SPARKS[:3]

    def test_measured_zero_is_not_missing_data(self):
        assert sparkline([0] * 60, 10, GPU_RAMP).plain == SPARKS[0] * 10
        assert sparkline([], 10, GPU_RAMP).plain == NO_DATA

    def test_ascii_fallback(self):
        text = sparkline([50] * 60, 10, GPU_RAMP, ascii_only=True).plain
        assert len(text) == 10
        assert " " not in text  # a blank would read as missing, not as a measured zero


class TestRamps:
    def test_scope_is_never_ambiguous(self):
        for value in (0, 10, 30, 60, 85, 100):
            assert ramp_style(value, GPU_RAMP) != ramp_style(value, HOST_RAMP)

    def test_the_low_end_is_a_single_colour(self):
        """Each glyph is coloured by its own value, so splitting "low" across bands makes
        an idle GPU draw as several colours at once."""
        assert len({ramp_style(v, GPU_RAMP) for v in (0, 1, 6, 12, 24)}) == 1
