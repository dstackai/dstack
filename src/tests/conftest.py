import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "ui: mark test as testing UI to run only with --runui")
    config.addinivalue_line(
        "markers", "postgres: mark test as testing Postgres to run only with --runpostgres"
    )


def pytest_addoption(parser):
    parser.addoption("--runui", action="store_true", default=False, help="Run UI tests")
    parser.addoption(
        "--runpostgres", action="store_true", default=False, help="Run tests with PostgreSQL"
    )


def pytest_collection_modifyitems(config, items):
    skip_ui = pytest.mark.skip(reason="need --runui option to run")
    skip_postgres = pytest.mark.skip(reason="need --runpostgres option to run")
    for item in items:
        if not config.getoption("--runui") and "ui" in item.keywords:
            item.add_marker(skip_ui)
        if not config.getoption("--runpostgres") and "postgres" in item.keywords:
            item.add_marker(skip_postgres)
