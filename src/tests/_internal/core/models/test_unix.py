import pytest

from dstack._internal.core.models.unix import UnixUser


class TestUnixUser:
    @pytest.mark.parametrize(
        ["value", "expected"],
        [
            ["0", UnixUser(uid=0)],
            ["1000", UnixUser(uid=1000)],
            ["debian", UnixUser(username="debian")],
            ["1000:2000", UnixUser(uid=1000, gid=2000)],
            ["1000:wheel", UnixUser(uid=1000, groupname="wheel")],
            ["root:0", UnixUser(username="root", gid=0)],
            ["admin:wheel", UnixUser(username="admin", groupname="wheel")],
        ],
    )
    def test_ok(self, value: str, expected: UnixUser):
        assert UnixUser.parse(value) == expected

    @pytest.mark.parametrize("value", ["1000:1000:", "user:group:foo:bar"])
    def test_too_many_parts(self, value: str):
        with pytest.raises(ValueError, match="too many parts"):
            UnixUser.parse(value)

    @pytest.mark.parametrize("value", ["", ":group"])
    def test_empty_user(self, value: str):
        with pytest.raises(ValueError, match="empty user name or id"):
            UnixUser.parse(value)

    @pytest.mark.parametrize("value", ["-1", "-1:group"])
    def test_negative_uid(self, value: str):
        with pytest.raises(ValueError, match="negative uid"):
            UnixUser.parse(value)

    def test_empty_group(self):
        with pytest.raises(ValueError, match="empty group name or id"):
            UnixUser.parse("user:")

    def test_negative_gid(self):
        with pytest.raises(ValueError, match="negative gid"):
            UnixUser.parse("1000:-1000")
