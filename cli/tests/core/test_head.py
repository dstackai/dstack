from typing import Optional

from dstack._internal.core.head import BaseHead


class TestHead(BaseHead):
    id: int
    a: str
    b: Optional[str]
    c: str

    @classmethod
    def prefix(cls) -> str:
        return "test/l;"


def test_prefix():
    assert TestHead.prefix() == "test/l;"


def test_decode():
    h = TestHead.decode("test/l;123;var;;a;b;c;d")
    assert h.id == 123
    assert h.a == "var"
    assert h.b == ""
    assert h.c == "a;b;c;d"


def test_encode():
    assert TestHead(id=123, a="var", c="a;b;c;d").encode() == "test/l;123;var;;a;b;c;d"
