import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from git import Repo

from dstack._internal.backend.local.runners import _install_runner_if_necessary

TESTS_DIR = HOME_DIR = Path("/tmp", "dstack-tests")
SSH_DIR = HOME_DIR / ".ssh"
DSTACK_DIR = TESTS_DIR / ".dstack"
DSTACK_HOMEDIR_WITH_RUNNER = TESTS_DIR / "dstack-runner"
TESTS_PUBLIC_DIR = TESTS_DIR / "dstack-tests-public"
TESTS_LOCAL_DIR = TESTS_DIR / "dstack-tests-local"
TESTS_PUBLIC_REPO_URL = "https://github.com/dstackai/dstack-tests-public"


@pytest.fixture(scope="session")
def local_runner():
    with patch("pathlib.Path.home", lambda: DSTACK_HOMEDIR_WITH_RUNNER):
        _install_runner_if_necessary()
    yield DSTACK_HOMEDIR_WITH_RUNNER / ".dstack"


@pytest.fixture
def dstack_dir(local_runner: Path):
    shutil.copytree(local_runner, DSTACK_DIR)
    SSH_DIR.mkdir(exist_ok=True)
    with patch("dstack._internal.cli.config.config.home", DSTACK_DIR):
        yield DSTACK_DIR
    # We need sudo to delete directories created by runner on Linux
    # See https://github.com/dstackai/dstack/issues/335
    try:
        shutil.rmtree(DSTACK_DIR)
    except PermissionError:
        subprocess.run(["sudo", "rm", "-r", DSTACK_DIR])


@pytest.fixture(scope="session")
def tests_public_repo():
    Repo.clone_from(TESTS_PUBLIC_REPO_URL, TESTS_PUBLIC_DIR)
    yield TESTS_PUBLIC_DIR
    shutil.rmtree(TESTS_PUBLIC_DIR)


@pytest.fixture()
def tests_local_repo():
    TESTS_LOCAL_DIR.mkdir(parents=True)
    yield TESTS_LOCAL_DIR
    shutil.rmtree(TESTS_LOCAL_DIR)
