import errno
import os
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional
from unittest.mock import patch

import psutil
import requests

from dstack.cli.main import main

HUB_HOST = "127.0.0.1"
HUB_PORT = "31313"
HUB_TOKEN = "test_token"


def run_dstack_cli(
    args: List[str],
    dstack_dir: Optional[Path] = None,
    repo_dir: Optional[Path] = None,
) -> int:
    exit_code = 0
    if repo_dir is not None:
        cwd = os.getcwd()
        os.chdir(repo_dir)
    if dstack_dir is not None:
        home_dir = os.environ["HOME"]
        new_home_dir = dstack_dir.parent
        os.environ["HOME"] = str(new_home_dir)
    with patch("sys.argv", ["dstack"] + args):
        try:
            main()
        except SystemExit as e:
            exit_code = e.code
    if dstack_dir is not None:
        os.environ["HOME"] = home_dir
    if repo_dir is not None:
        os.chdir(cwd)
    return exit_code


@contextmanager
def hub_process(dstack_dir: Path) -> subprocess.Popen:
    proc = run_dstack_subprocess(
        ["start", "--host", HUB_HOST, "--port", HUB_PORT, "--token", HUB_TOKEN],
        dstack_dir=dstack_dir,
    )
    with terminate_on_exit(proc):
        wait_hub()
        yield proc


def run_dstack_subprocess(
    args: List[str],
    dstack_dir: Optional[Path] = None,
    repo_dir: Optional[Path] = None,
) -> subprocess.Popen:
    cwd = os.getcwd()
    if repo_dir is not None:
        cwd = repo_dir
    env = os.environ.copy()
    if dstack_dir:
        env["HOME"] = dstack_dir.parent
        env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        args=["dstack"] + args,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        text=True,
    )
    return proc


@contextmanager
def terminate_on_exit(proc: subprocess.Popen) -> subprocess.Popen:
    try:
        yield proc
    finally:
        process = psutil.Process(proc.pid)
        for child in process.children(recursive=True):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                continue
        try:
            process.kill()
        except psutil.NoSuchProcess:
            pass


# TODO: Figure out a way to read process stderr reliably.
# proc.communicate() may hang even with timeout.
#
# @contextmanager
# def terminate_on_exit(proc: subprocess.Popen) -> subprocess.Popen:
#     try:
#         yield proc
#     finally:
#         stderr = None
#         try:
#             stdout, stderr = proc.communicate(timeout=1)
#         except subprocess.TimeoutExpired as e:
#             process = psutil.Process(proc.pid)
#             for child in process.children(recursive=True):
#                 child.kill()
#             process.kill()
#             stdout, stderr = proc.communicate()
#         if stderr is not None:
#             print(stderr)


def wait_hub(host: str = HUB_HOST, port: str = HUB_PORT, attempts=10):
    for _ in range(attempts):
        try:
            resp = requests.get(f"http://{host}:{port}")
        except requests.exceptions.ConnectionError:
            time.sleep(1)
            continue
        if resp.status_code == 200:
            return True
        else:
            assert False, (resp.status_code, resp.content)
    assert False
