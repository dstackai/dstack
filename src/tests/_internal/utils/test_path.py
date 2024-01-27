from pathlib import PurePath

import pytest

from dstack._internal.utils.path import resolve_relative_path


class TestResolveRelativePath:
    def test_abs_path(self):
        with pytest.raises(ValueError):
            resolve_relative_path("/tmp")

    def test_escape_repo(self):
        with pytest.raises(ValueError):
            resolve_relative_path("repo/../..")

    def test_normalize(self):
        assert resolve_relative_path("repo/./../repo2") == PurePath("repo2")
