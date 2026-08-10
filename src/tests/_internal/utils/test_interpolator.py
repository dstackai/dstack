import pytest

from dstack._internal.utils.interpolator import InterpolatorError, VariablesInterpolator
from dstack._internal.utils.nodes_interpolator import is_valid_groups_ip_ref


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

    def test_skips_groups_refs(self):
        s = "ray start --address=${{ groups[0].nodes[0].IP_ADDRESS }}:6379"
        interpolator = VariablesInterpolator(
            {"run": {"args": "x"}},
            skip={"groups": is_valid_groups_ip_ref},
        )
        assert interpolator.interpolate(s) == s

    def test_rejects_invalid_groups_refs(self):
        interpolator = VariablesInterpolator(
            {"run": {"args": "x"}},
            skip={"groups": is_valid_groups_ip_ref},
        )
        with pytest.raises(InterpolatorError, match="Illegal reference name"):
            interpolator.interpolate("${{ groups[0].nodes[0].IP }}")
        with pytest.raises(InterpolatorError, match="Illegal reference name"):
            interpolator.interpolate("${{ groups[0].node[0].IP_ADDRESS }}")
        with pytest.raises(InterpolatorError, match="Illegal reference name"):
            interpolator.interpolate("${{ groups.prefill.nodes[0].IP_ADDRESS }}")
