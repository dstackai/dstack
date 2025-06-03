import io
import tarfile
from pathlib import Path

import pytest

from dstack._internal.core.models.repos.local import LocalRepo


class TestRepoPathType:
    REPO_DIR_NAME = "repo"

    @pytest.fixture
    def repo_parent_dir(self, tmp_path: Path) -> Path:
        repo_dir = tmp_path / self.REPO_DIR_NAME
        repo_dir.mkdir()
        (repo_dir / "file.txt").touch()
        (repo_dir / "inner").mkdir()
        (repo_dir / "inner" / "file.txt").mkdir()
        return tmp_path

    @staticmethod
    def check(repo: LocalRepo) -> None:
        fp = io.BytesIO()
        repo.write_code_file(fp)
        fp.seek(0)
        with tarfile.open(fileobj=fp, mode="r") as tar:
            names = tar.getnames()
            assert "file.txt" in names
            assert "inner/file.txt" in names

    def test_absolute(self, repo_parent_dir: Path):
        repo = LocalRepo.from_dir(repo_parent_dir.resolve() / self.REPO_DIR_NAME)
        self.check(repo)

    def test_relative(self, repo_parent_dir: Path, monkeypatch):
        monkeypatch.chdir(repo_parent_dir)
        repo = LocalRepo.from_dir(self.REPO_DIR_NAME)
        self.check(repo)

    def test_cwd(self, repo_parent_dir: Path, monkeypatch):
        monkeypatch.chdir(repo_parent_dir / self.REPO_DIR_NAME)
        repo = LocalRepo.from_dir(".")
        self.check(repo)

    def test_with_parent_reference(self, repo_parent_dir: Path, monkeypatch):
        cwd = repo_parent_dir / "test"
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        repo = LocalRepo.from_dir(Path("..") / self.REPO_DIR_NAME)
        self.check(repo)


def test_ignore_rules(tmp_path: Path):
    (tmp_path / "file1.txt").touch()
    (tmp_path / "file2.py").touch()
    (tmp_path / ".hidden").touch()
    (tmp_path / ".dstackignore").write_text("file2.py\n")
    (tmp_path / "inner").mkdir()
    (tmp_path / "inner" / "file3.txt").touch()
    (tmp_path / "inner" / "file4.py").touch()
    (tmp_path / "inner" / ".gitignore").write_text("*.txt")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").touch()

    repo = LocalRepo.from_dir(tmp_path)
    fp = io.BytesIO()
    repo.write_code_file(fp)
    fp.seek(0)

    with tarfile.open(fileobj=fp, mode="r") as tar:
        names = tar.getnames()
        assert "file1.txt" in names
        assert "file2.py" not in names  # ignored by .dstackignore
        assert ".hidden" in names
        assert ".dstackignore" in names
        assert "inner/file3.txt" not in names  # ignored by inner/.gitignore
        assert "inner/file4.py" in names
        assert ".git/config" not in names  # .git always ignored
