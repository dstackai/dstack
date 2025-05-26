import tempfile
from pathlib import Path

from dstack._internal.utils.ignore import GitIgnore


class TestGitIgnore:
    def test_basic_gitignore_functionality(self):
        """Test basic .gitignore pattern matching."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "test"
            test_dir.mkdir()

            # Create .gitignore
            gitignore_file = test_dir / ".gitignore"
            gitignore_file.write_text("*.log\ntemp/\n__pycache__/\n")

            git_ignore = GitIgnore(test_dir)

            # Test file patterns
            assert git_ignore.ignore("test.log") is True
            assert git_ignore.ignore("debug.log") is True
            assert git_ignore.ignore("test.txt") is False
            assert git_ignore.ignore("script.py") is False

            # Test directory patterns
            assert git_ignore.ignore("temp") is True
            assert git_ignore.ignore("temp/") is True
            assert git_ignore.ignore("temp/file.txt") is True
            assert git_ignore.ignore("__pycache__") is True
            assert git_ignore.ignore("__pycache__/module.pyc") is True

    def test_nested_gitignore_files(self):
        """Test that nested .gitignore files are loaded recursively."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "test"
            test_dir.mkdir()

            # Root .gitignore
            (test_dir / ".gitignore").write_text("*.log\n")

            # Nested directory with its own .gitignore
            subdir = test_dir / "subdir"
            subdir.mkdir()
            (subdir / ".gitignore").write_text("*.tmp\n")

            # Create actual files for testing (gitignore_parser may need them)
            (test_dir / "test.log").touch()
            (subdir / "test.log").touch()
            (subdir / "file.tmp").touch()
            (test_dir / "file.tmp").touch()

            git_ignore = GitIgnore(test_dir)

            # Test patterns from root .gitignore
            assert git_ignore.ignore("test.log") is True
            assert git_ignore.ignore("subdir/test.log") is True

            # Test patterns from nested .gitignore
            assert git_ignore.ignore("subdir/file.tmp") is True
            # Files outside the subdir should not be matched by subdir's .gitignore
            assert git_ignore.ignore("file.tmp") is False

    def test_dstackignore_file(self):
        """Test that .dstackignore files are processed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "test"
            test_dir.mkdir()

            # Create .dstackignore
            dstackignore_file = test_dir / ".dstackignore"
            dstackignore_file.write_text("*.cache\ndata/\n")

            git_ignore = GitIgnore(test_dir)

            assert git_ignore.ignore("file.cache") is True
            assert git_ignore.ignore("data") is True
            assert git_ignore.ignore("data/dataset.csv") is True
            assert git_ignore.ignore("file.txt") is False

    def test_git_info_exclude(self):
        """Test that .git/info/exclude files are processed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "test"
            test_dir.mkdir()

            # Create .git/info/exclude in the root directory
            git_info_dir = test_dir / ".git" / "info"
            git_info_dir.mkdir(parents=True)
            exclude_file = git_info_dir / "exclude"
            exclude_file.write_text("*.exclude\nbuild/\n")

            git_ignore = GitIgnore(test_dir)

            # .git/info/exclude should apply to the entire repository
            assert git_ignore.ignore("file.exclude") is True
            assert git_ignore.ignore("build") is True
            assert git_ignore.ignore("build/output.txt") is True
            assert git_ignore.ignore("subdir/file.exclude") is True
            assert git_ignore.ignore("file.txt") is False

    def test_custom_ignore_files(self):
        """Test custom ignore file names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "test"
            test_dir.mkdir()

            # Create custom ignore file
            custom_ignore = test_dir / ".myignore"
            custom_ignore.write_text("*.custom\n")

            git_ignore = GitIgnore(test_dir, ignore_files=[".myignore"])

            assert git_ignore.ignore("file.custom") is True
            assert git_ignore.ignore("file.txt") is False

    def test_additional_globs(self):
        """Test additional glob patterns passed to constructor."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "test"
            test_dir.mkdir()

            git_ignore = GitIgnore(test_dir, globs=["*.pyc", "node_modules/"])

            assert git_ignore.ignore("module.pyc") is True
            assert git_ignore.ignore("node_modules") is True
            assert git_ignore.ignore("node_modules/package.json") is True
            assert git_ignore.ignore("script.py") is False

    def test_combined_ignore_sources(self):
        """Test combination of .gitignore, custom files, and globs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "test"
            test_dir.mkdir()

            # Create .gitignore
            (test_dir / ".gitignore").write_text("*.log\n")

            # Create .dstackignore
            (test_dir / ".dstackignore").write_text("*.cache\n")

            git_ignore = GitIgnore(test_dir, globs=["*.tmp"])

            assert git_ignore.ignore("file.log") is True  # from .gitignore
            assert git_ignore.ignore("file.cache") is True  # from .dstackignore
            assert git_ignore.ignore("file.tmp") is True  # from globs
            assert git_ignore.ignore("file.txt") is False

    def test_absolute_paths(self):
        """Test handling of absolute paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "test"
            test_dir.mkdir()

            # Create .gitignore
            (test_dir / ".gitignore").write_text("*.log\n")

            git_ignore = GitIgnore(test_dir)

            # Test absolute path within repo
            abs_path = test_dir / "test.log"
            assert git_ignore.ignore(abs_path) is True

            # Test absolute path outside repo
            outside_path = Path(tmpdir) / "outside.log"
            assert git_ignore.ignore(outside_path) is False

    def test_empty_path(self):
        """Test handling of empty paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "test"
            test_dir.mkdir()

            git_ignore = GitIgnore(test_dir)

            assert git_ignore.ignore("") is False
            assert git_ignore.ignore(None) is False

    def test_nonexistent_ignore_files(self):
        """Test that nonexistent ignore files are handled gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "test"
            test_dir.mkdir()

            # No ignore files exist
            git_ignore = GitIgnore(test_dir)

            # Should not ignore anything
            assert git_ignore.ignore("any_file.txt") is False
            assert git_ignore.ignore("any_dir/") is False

    def test_malformed_ignore_files(self):
        """Test handling of malformed ignore files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "test"
            test_dir.mkdir()

            # Create a file that might cause parsing issues
            gitignore_file = test_dir / ".gitignore"
            gitignore_file.write_text("*.log\n# comment\n\n  \n*.tmp\n")

            git_ignore = GitIgnore(test_dir)

            # Should still work for valid patterns
            assert git_ignore.ignore("test.log") is True
            assert git_ignore.ignore("test.tmp") is True
            assert git_ignore.ignore("test.txt") is False

    def test_directory_traversal_stops_at_ignored_dirs(self):
        """Test that ignored directories don't have their subdirectories processed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "test"
            test_dir.mkdir()

            # Create root .gitignore that ignores 'ignored_dir'
            (test_dir / ".gitignore").write_text("ignored_dir/\n")

            # Create ignored directory with its own .gitignore
            ignored_dir = test_dir / "ignored_dir"
            ignored_dir.mkdir()
            (ignored_dir / ".gitignore").write_text("*.should_not_apply\n")

            # Create a subdirectory in the ignored directory
            subdir = ignored_dir / "subdir"
            subdir.mkdir()
            (subdir / ".gitignore").write_text("*.also_should_not_apply\n")

            git_ignore = GitIgnore(test_dir)

            # The ignored directory itself should be ignored
            assert git_ignore.ignore("ignored_dir") is True
            assert git_ignore.ignore("ignored_dir/file.txt") is True

            # Patterns from .gitignore files inside ignored directories should not apply
            # to files outside those directories
            assert git_ignore.ignore("file.should_not_apply") is False
            assert git_ignore.ignore("file.also_should_not_apply") is False

    def test_relative_path_handling(self):
        """Test various relative path formats."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "test"
            test_dir.mkdir()

            (test_dir / ".gitignore").write_text("*.log\ntemp/\n")

            git_ignore = GitIgnore(test_dir)

            # Test different path formats
            assert git_ignore.ignore("file.log") is True
            assert git_ignore.ignore("./file.log") is True
            assert git_ignore.ignore("subdir/file.log") is True
            assert git_ignore.ignore("./subdir/file.log") is True
            assert git_ignore.ignore("temp") is True
            assert git_ignore.ignore("./temp") is True
            assert git_ignore.ignore("temp/") is True
