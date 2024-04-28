from pathlib import Path

from dstack.api.utils import load_profile


class TestLoadProfile:
    def test_loads_empty_profile_when_no_profiles(self, monkeypatch, tmpdir):
        test_dir = Path(tmpdir)
        repo_dir = test_dir / "repo"
        home_dir = test_dir / "home_dir"
        monkeypatch.setattr(Path, "home", lambda: home_dir)
        load_profile(repo_dir, profile_name=None)
