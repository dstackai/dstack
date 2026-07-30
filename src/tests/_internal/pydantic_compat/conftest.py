import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--regen-fixtures",
        action="store_true",
        default=False,
        help="Rewrite the pydantic_compat fixtures instead of asserting against them",
    )


def pytest_collection_modifyitems(config, items):
    """
    Mark everything in this package `pydantic_compat` so `--pydantic-compat` gates it.

    Applied here rather than as a `pytestmark` in each module so a module added later cannot
    silently escape the gate and start failing regular CI.
    """
    package_dir = __file__.rsplit("/", 1)[0]
    for item in items:
        if str(item.path).startswith(package_dir):
            item.add_marker(pytest.mark.pydantic_compat)


@pytest.fixture
def regen(request) -> bool:
    return request.config.getoption("--regen-fixtures")
