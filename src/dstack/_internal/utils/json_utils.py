from typing import Any

import orjson
from pydantic import BaseModel

FREEZEGUN = True
try:
    from freezegun.api import FakeDatetime
except ImportError:
    FREEZEGUN = False


ASYNCPG = True
try:
    import asyncpg.pgproto.pgproto
except ImportError:
    ASYNCPG = False


def pydantic_orjson_dumps(v: Any, *, default: Any) -> str:
    return orjson.dumps(
        v,
        option=get_orjson_default_options(),
        default=orjson_default,
    ).decode()


def pydantic_orjson_dumps_with_indent(v: Any, *, default: Any) -> str:
    return orjson.dumps(
        v,
        option=get_orjson_default_options() | orjson.OPT_INDENT_2,
        default=orjson_default,
    ).decode()


def orjson_default(obj):
    if isinstance(obj, float):
        # orjson does not convert float subclasses be default
        return float(obj)
    if isinstance(obj, BaseModel):
        # Allows calling orjson.dumps() on pydantic models
        # (e.g. to return from the API)
        return obj.dict()
    if ASYNCPG:
        if isinstance(obj, asyncpg.pgproto.pgproto.UUID):
            return str(obj)
    if FREEZEGUN:
        if isinstance(obj, FakeDatetime):
            return obj.isoformat()
    raise TypeError


def get_orjson_default_options() -> int:
    return orjson.OPT_NON_STR_KEYS
