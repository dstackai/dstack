import inspect
import os

import pytest

from dstack._internal.server.testing.conf import (  # noqa: F401
    postgres_container,
    postgres_db,
    session,
    sqlite_db,
    test_db,
)
from dstack._internal.settings import FeatureFlags
from dstack._internal.utils import crypto


def pytest_configure(config):
    config.addinivalue_line("markers", "ui: mark test as testing UI to run only with --runui")
    config.addinivalue_line(
        "markers", "postgres: mark test as testing Postgres to run only with --runpostgres"
    )
    config.addinivalue_line(
        "markers", "windows: mark test to be run on Windows in addition to POSIX"
    )
    config.addinivalue_line("markers", "windows_only: mark test to be run on Windows only")
    config.addinivalue_line(
        "markers",
        "pydantic_compat: mark test as a pydantic v1/v2 compat check to run only with"
        " --pydantic-compat",
    )


def pytest_addoption(parser):
    parser.addoption("--runui", action="store_true", default=False, help="Run UI tests")
    parser.addoption(
        "--runpostgres", action="store_true", default=False, help="Run tests with PostgreSQL"
    )
    parser.addoption(
        "--pydantic-compat",
        action="store_true",
        default=False,
        help="Run the pydantic v1/v2 compat fixtures (src/tests/_internal/pydantic_compat)",
    )


def pytest_collection_modifyitems(config, items):
    skip_ui = pytest.mark.skip(reason="need --runui option to run")
    skip_postgres = pytest.mark.skip(reason="need --runpostgres option to run")
    skip_pydantic_compat = pytest.mark.skip(reason="need --pydantic-compat option to run")
    is_windows = os.name == "nt"
    skip_posix = pytest.mark.skip(reason="requires POSIX")
    skip_windows = pytest.mark.skip(reason="requires Windows")
    for item in items:
        if not config.getoption("--runui") and "ui" in item.keywords:
            item.add_marker(skip_ui)
        if not config.getoption("--runpostgres") and "postgres" in item.keywords:
            item.add_marker(skip_postgres)
        if not config.getoption("--pydantic-compat") and "pydantic_compat" in item.keywords:
            item.add_marker(skip_pydantic_compat)
        for_windows_only = "windows_only" in item.keywords
        for_windows = for_windows_only or "windows" in item.keywords
        if for_windows_only and not is_windows:
            item.add_marker(skip_windows)
        if not for_windows and is_windows:
            item.add_marker(skip_posix)


@pytest.fixture(scope="session", autouse=True)
def reuse_one_rsa_key_pair():
    """
    Hands the same RSA key pair to every caller for the whole test session.

    Generating a 2048-bit key takes ~80ms and the server generates one per user, project,
    gateway, and job. A test that needs two different keys has to generate its own.
    """
    private_bytes, public_bytes = crypto.generate_rsa_key_pair_bytes()
    public_key = public_bytes.rsplit(b" ", 1)[0]  # drop the comment, callers pass their own

    def generate_rsa_key_pair_bytes(comment: str = "dstack") -> tuple[bytes, bytes]:
        return private_bytes, public_key + f" {comment}\n".encode()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(crypto, "generate_rsa_key_pair_bytes", generate_rsa_key_pair_bytes)
        yield


@pytest.fixture(scope="session", autouse=True)
def disable_feature_flags():
    """
    Disables all feature flags once per test session.

    If you need to test a feature flag, monkeypatch `FeatureFlags` class on a per-test basis.
    """
    for name, value in inspect.getmembers(FeatureFlags):
        if not name.startswith("_") and name.isupper():
            if not isinstance(value, bool):
                raise RuntimeError(f"FeatureFlags.{name}: only bool values are supported")
            setattr(FeatureFlags, name, False)
