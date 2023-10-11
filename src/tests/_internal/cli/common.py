import os
from pathlib import Path
from typing import List, Optional
from unittest.mock import patch

from dstack._internal.cli.main import main


def run_dstack_cli(
    args: List[str],
    home_dir: Optional[Path] = None,
    repo_dir: Optional[Path] = None,
) -> int:
    exit_code = 0
    if repo_dir is not None:
        cwd = os.getcwd()
        os.chdir(repo_dir)
    if home_dir is not None:
        prev_home_dir = os.environ["HOME"]
        os.environ["HOME"] = str(home_dir)
    with patch("sys.argv", ["dstack"] + args):
        try:
            main()
        except SystemExit as e:
            exit_code = e.code
    if home_dir is not None:
        os.environ["HOME"] = prev_home_dir
    if repo_dir is not None:
        os.chdir(cwd)
    return exit_code
