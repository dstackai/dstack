import pytest
from pydantic import ValidationError

from dstack._internal.core.backends.vastai.profile_options import VastAIProfileOptions
from dstack._internal.core.models.profiles import Profile


class TestValidateProfileBackendOptions:
    def test_duplicate_backend_type_raises_validation_error(self):
        with pytest.raises(ValidationError, match="duplicate entry for backend 'vastai'"):
            Profile(
                backend_options=[
                    VastAIProfileOptions(min_score=100),
                    VastAIProfileOptions(min_score=200),
                ]
            )

    def test_single_entry_per_backend_is_valid(self):
        profile = Profile(backend_options=[VastAIProfileOptions(min_score=100)])
        assert profile.backend_options is not None
        assert len(profile.backend_options) == 1

    def test_none_backend_options_is_valid(self):
        profile = Profile(backend_options=None)
        assert profile.backend_options is None

    def test_empty_list_backend_options_is_valid(self):
        profile = Profile(backend_options=[])
        assert profile.backend_options == []
