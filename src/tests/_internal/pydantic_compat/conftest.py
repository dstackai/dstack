import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--regen-fixtures",
        action="store_true",
        default=False,
        help="Rewrite the pydantic_compat fixtures instead of asserting against them",
    )


@pytest.fixture
def regen(request) -> bool:
    return request.config.getoption("--regen-fixtures")
