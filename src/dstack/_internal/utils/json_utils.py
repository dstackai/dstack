import orjson
from pydantic import BaseModel

FREEZEGUN = True
try:
    from freezegun.api import FakeDatetime
except ImportError:
    FREEZEGUN = False


def orjson_default(obj):
    if isinstance(obj, float):
        # orjson does not convert float subclasses be default
        return float(obj)
    if isinstance(obj, BaseModel):
        # Allows calling orjson.dumps() on pydantic models
        # (e.g. to return from the API)
        return obj.dict()
    if FREEZEGUN:
        if isinstance(obj, FakeDatetime):
            return obj.isoformat()
    raise TypeError


def get_orjson_options() -> int:
    return orjson.OPT_NON_STR_KEYS
