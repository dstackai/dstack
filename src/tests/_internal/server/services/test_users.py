import pytest

from dstack._internal.server.services.users import is_valid_username


class TestIsValidUsername:
    @pytest.mark.parametrize(
        "username",
        [
            "special#$symbols",
            "A,B",
            "",
            "a" * 61,
        ],
    )
    def test_valid(self, username: str):
        assert not is_valid_username(username)

    @pytest.mark.parametrize(
        "username",
        [
            "regularusername",
            "CaseUsername",
            "username_with_underscores-and-dashes1234",
            "a" * 60,
        ],
    )
    def test_invalid(self, username: str):
        assert is_valid_username(username)
