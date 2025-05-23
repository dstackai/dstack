import os
from pathlib import Path
from typing import List

from gitignore_parser import parse_gitignore_str

from dstack._internal.utils.path import PathLike


class GitIgnore:
    def __init__(
        self, root_dir: PathLike, ignore_files: List[str] = None, globs: List[str] = None
    ):
        self.root_dir = Path(root_dir)
        self.ignore_files = (
            ignore_files
            if ignore_files is not None
            else [".gitignore", ".git/info/exclude", ".dstackignore"]
        )
        self.parser = None
        self._create_combined_parser(globs or [])

    def _create_combined_parser(self, additional_globs: List[str]):
        """Create a single parser from all ignore files and additional globs."""
        all_patterns = []

        # Collect patterns from all ignore files recursively
        self._collect_patterns_recursive(self.root_dir, all_patterns)

        # Add additional glob patterns
        all_patterns.extend(additional_globs)

        self.parser = parse_gitignore_str("\n".join(all_patterns), self.root_dir)

    def _collect_patterns_recursive(self, path: Path, patterns: List[str]):
        """
        Recursively collect patterns from all ignore files and combine them into a single gitignore,
        with the root directory as the base path.
        """
        for ignore_file_name in self.ignore_files:
            ignore_file = path / ignore_file_name
            if ignore_file.exists():
                try:
                    # Get relative path from root to this directory
                    if path == self.root_dir:
                        prefix = ""
                    else:
                        prefix = path.relative_to(self.root_dir)

                    # Read patterns and prefix them with directory path
                    with ignore_file.open("r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#"):
                                if prefix:
                                    # Prefix patterns with directory path for subdirectories
                                    if line.startswith("/"):
                                        # Absolute pattern within subdirectory
                                        patterns.append(os.path.join(prefix, line[1:]))
                                    else:
                                        # Relative pattern within subdirectory
                                        # Add pattern that matches files directly in the subdirectory
                                        patterns.append(os.path.join(prefix, line))
                                        # Add pattern that matches files in deeper subdirectories
                                        patterns.append(os.path.join(prefix, "**", line))
                                else:
                                    # Root directory patterns
                                    patterns.append(line)
                except (OSError, UnicodeDecodeError):
                    # Skip files we can't read
                    continue

        # Recursively process subdirectories
        # Note: We need to check if directories should be ignored, but we can't
        # use self.ignore() yet since we're still building the parser
        # So we'll process all directories and let gitignore_parser handle the logic
        try:
            for subdir in path.iterdir():
                if subdir.is_dir():
                    self._collect_patterns_recursive(subdir, patterns)
        except (OSError, PermissionError):
            # Skip directories we can't read
            pass

    def ignore(self, path: PathLike) -> bool:
        """Check if a path should be ignored."""
        if not path or not self.parser:
            return False

        path = Path(path)
        if path.is_absolute():
            try:
                path = path.relative_to(self.root_dir)
            except ValueError:
                return False

        # Convert to absolute path for gitignore_parser
        abs_path = str(self.root_dir / path)
        return self.parser(abs_path)
