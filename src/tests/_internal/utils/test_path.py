from pathlib import PurePath

import pytest

from dstack._internal.utils.path import normalize_path, resolve_relative_path


class TestNormalizePath:
    def test_escape_top(self):
        with pytest.raises(ValueError):
            normalize_path("dir/../..")

    def test_normalize_rel(self):
        assert normalize_path("dir/.///..///sibling") == PurePath("sibling")

    def test_normalize_abs(self):
        assert normalize_path("/dir/.///..///sibling") == PurePath("/sibling")


class TestResolveRelativePath:
    def test_abs_path(self):
        with pytest.raises(ValueError):
            resolve_relative_path("/tmp")

    def test_escape_repo(self):
        with pytest.raises(ValueError):
            resolve_relative_path("repo/../..")

    def test_normalize(self):
        assert resolve_relative_path("repo/./../repo2") == PurePath("repo2")
