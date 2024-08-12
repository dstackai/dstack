import pytest

from dstack._internal.utils.interpolator import InterpolatorError, VariablesInterpolator


def get_interpolator():
    return VariablesInterpolator({"run": {"args": "qwerty"}}, skip=["secrets"])


class TestVariablesInterpolator:
    def test_empty(self):
        s = ""
        assert s == get_interpolator().interpolate(s)

    def test_bash(self):
        s = "${ENV}"
        assert s == get_interpolator().interpolate(s)

    def test_escaped_dollar(self):
        assert "${{ENV}}" == get_interpolator().interpolate("$${{ENV}}")

    def test_escaped_dollar_middle(self):
        assert "echo ${{ENV}}" == get_interpolator().interpolate("echo $${{ENV}}")

    def test_args(self):
        assert "qwerty" == get_interpolator().interpolate("${{ run.args }}")

    def test_secrets(self):
        s = "${{ secrets.password  }}"
        assert s == get_interpolator().interpolate(s)

    def test_missing(self):
        s, missing = get_interpolator().interpolate("${{ env.name }}", return_missing=True)
        assert "" == s
        assert ["env.name"] == missing

    def test_unclosed_pattern(self):
        with pytest.raises(InterpolatorError):
            get_interpolator().interpolate("${{ secrets.password }")

    def test_illegal_name(self):
        with pytest.raises(InterpolatorError):
            get_interpolator().interpolate("${{ secrets.pass-word }}")
        with pytest.raises(InterpolatorError):
            get_interpolator().interpolate("${{ .password }}")
        with pytest.raises(InterpolatorError):
            get_interpolator().interpolate("${{ password. }}")
        with pytest.raises(InterpolatorError):
            get_interpolator().interpolate("${{ secrets.password.hash }}")
        with pytest.raises(InterpolatorError):
            get_interpolator().interpolate("${{ secrets.007 }}")
