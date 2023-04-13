import os
import shutil
import subprocess
from pathlib import Path
from typing import Tuple
from unittest.mock import patch

import pytest
from cryptography.hazmat.backends import default_backend as crypto_default_backend
from cryptography.hazmat.primitives import serialization as crypto_serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from git import Repo

from dstack.backend.local.runners import _install_runner_if_necessary

TESTS_DIR = HOME_DIR = Path("/tmp", "dstack-tests")
SSH_DIR = HOME_DIR / ".ssh"
DSTACK_DIR = TESTS_DIR / ".dstack"
DSTACK_HOMEDIR_WITH_RUNNER = TESTS_DIR / "dstack-runner"
TESTS_PUBLIC_DIR = TESTS_DIR / "dstack-tests-public"
TESTS_PUBLIC_REPO_URL = "https://github.com/dstackai/dstack-tests-public"


@pytest.fixture(scope="session")
def local_runner():
    with patch("pathlib.Path.home", lambda: DSTACK_HOMEDIR_WITH_RUNNER):
        _install_runner_if_necessary()
    yield DSTACK_HOMEDIR_WITH_RUNNER / ".dstack"


@pytest.fixture
def dstack_dir(local_runner: Path):
    shutil.copytree(local_runner, DSTACK_DIR)
    yield DSTACK_DIR
    # We need sudo to delete directories created by runner
    subprocess.run(["sudo", "rm", "-r", DSTACK_DIR])


@pytest.fixture
def ssh_key():
    os.mkdir(SSH_DIR)
    _create_ssh_key_files(SSH_DIR)
    yield
    shutil.rmtree(SSH_DIR)


@pytest.fixture(scope="session")
def tests_public_repo():
    Repo.clone_from(TESTS_PUBLIC_REPO_URL, TESTS_PUBLIC_DIR)
    yield TESTS_PUBLIC_DIR
    shutil.rmtree(TESTS_PUBLIC_DIR)


def _generate_ssh_key() -> Tuple[bytes, bytes]:
    key = rsa.generate_private_key(
        backend=crypto_default_backend(), public_exponent=65537, key_size=2048
    )
    private_key = key.private_bytes(
        crypto_serialization.Encoding.PEM,
        crypto_serialization.PrivateFormat.PKCS8,
        crypto_serialization.NoEncryption(),
    )
    public_key = key.public_key().public_bytes(
        crypto_serialization.Encoding.OpenSSH, crypto_serialization.PublicFormat.OpenSSH
    )
    return private_key, public_key


PRIVATE_KEY, PUBLIC_KEY = _generate_ssh_key()


def _create_ssh_key_files(ssh_dir: Path):
    with open(ssh_dir / "id_rsa", "wb+") as f:
        f.write(PRIVATE_KEY)
    with open(ssh_dir / "id_rsa.pub", "wb+") as f:
        f.write(PUBLIC_KEY)
