import os

import pytest

from dstack._internal.server.testing.conf import postgres_container, session, test_db  # noqa: F401


def pytest_configure(config):
    config.addinivalue_line("markers", "ui: mark test as testing UI to run only with --runui")
    config.addinivalue_line(
        "markers", "postgres: mark test as testing Postgres to run only with --runpostgres"
    )
    config.addinivalue_line(
        "markers", "windows: mark test to be run on Windows in addition to POSIX"
    )
    config.addinivalue_line("markers", "windows_only: mark test to be run on Windows only")


def pytest_addoption(parser):
    parser.addoption("--runui", action="store_true", default=False, help="Run UI tests")
    parser.addoption(
        "--runpostgres", action="store_true", default=False, help="Run tests with PostgreSQL"
    )


def pytest_collection_modifyitems(config, items):
    skip_ui = pytest.mark.skip(reason="need --runui option to run")
    skip_postgres = pytest.mark.skip(reason="need --runpostgres option to run")
    is_windows = os.name == "nt"
    skip_posix = pytest.mark.skip(reason="requires POSIX")
    skip_windows = pytest.mark.skip(reason="requires Windows")
    for item in items:
        if not config.getoption("--runui") and "ui" in item.keywords:
            item.add_marker(skip_ui)
        if not config.getoption("--runpostgres") and "postgres" in item.keywords:
            item.add_marker(skip_postgres)
        for_windows_only = "windows_only" in item.keywords
        for_windows = for_windows_only or "windows" in item.keywords
        if for_windows_only and not is_windows:
            item.add_marker(skip_windows)
        if not for_windows and is_windows:
            item.add_marker(skip_posix)
