from dstack._internal.core.backends.base.profile_options import get_backend_profile_options
from dstack._internal.core.backends.vastai.profile_options import (
    VastAIProfileOptions,
)


class TestGetBackendProfileOptions:
    def test_returns_none_for_empty_list(self):
        assert get_backend_profile_options([], VastAIProfileOptions) is None

    def test_returns_none_for_none(self):
        assert get_backend_profile_options(None, VastAIProfileOptions) is None

    def test_returns_matching_option(self):
        opts = [VastAIProfileOptions(min_score=500)]
        result = get_backend_profile_options(opts, VastAIProfileOptions)
        assert isinstance(result, VastAIProfileOptions)
        assert result.min_score == 500
