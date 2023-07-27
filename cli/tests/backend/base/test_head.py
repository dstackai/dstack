from typing import Optional

from pydantic import BaseModel

from dstack._internal.backend.base.head import StorableHead


class TestHead(BaseModel):
    id: int
    a: str
    b: Optional[str]
    c: str


class TestHeadStorable(TestHead, StorableHead):
    @classmethod
    def prefix(cls) -> str:
        return "test/l;"


def test_prefix():
    assert TestHeadStorable.prefix() == "test/l;"


def test_decode():
    h = TestHeadStorable.decode("test/l;123;var;;a;b;c;d")
    assert h.id == 123
    assert h.a == "var"
    assert h.b == ""
    assert h.c == "a;b;c;d"


def test_encode():
    assert TestHeadStorable(id=123, a="var", c="a;b;c;d").encode() == "test/l;123;var;;a;b;c;d"
