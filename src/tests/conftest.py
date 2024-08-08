import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "ui: mark test as testing UI to run only with --runui")


def pytest_addoption(parser):
    parser.addoption("--runui", action="store_true", default=False, help="Run UI tests")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--runui"):
        return
    skip_slow = pytest.mark.skip(reason="need --runui option to run")
    for item in items:
        if "ui" in item.keywords:
            item.add_marker(skip_slow)
