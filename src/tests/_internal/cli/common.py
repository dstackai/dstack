import os
from pathlib import Path
from typing import List, Optional
from unittest.mock import patch

from dstack._internal.cli.main import main
from dstack._internal.compat import IS_WINDOWS


def run_dstack_cli(
    cli_args: List[str],
    home_dir: Optional[Path] = None,
    repo_dir: Optional[Path] = None,
) -> int:
    exit_code = 0
    if repo_dir is not None:
        cwd = os.getcwd()
        os.chdir(repo_dir)
    if home_dir is not None:
        prev_home_dir = os.environ.get("HOME")
        os.environ["HOME"] = str(home_dir)
        if IS_WINDOWS:
            prev_userprofile = os.environ.get("USERPROFILE")
            os.environ["USERPROFILE"] = str(home_dir)
    with patch("sys.argv", ["dstack"] + cli_args):
        try:
            main()
        except SystemExit as e:
            exit_code = e.code
        finally:
            if home_dir is not None:
                if prev_home_dir is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = prev_home_dir
                if IS_WINDOWS:
                    if prev_userprofile is None:
                        os.environ.pop("USERPROFILE", None)
                    else:
                        os.environ["USERPROFILE"] = prev_userprofile
            if repo_dir is not None:
                os.chdir(cwd)
    return exit_code
