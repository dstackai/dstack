import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


def get_persistent_path() -> Path:
    return Path("~/dstack/state.json").expanduser().resolve()


@lru_cache()
def get_persistent_state() -> Dict:
    path = get_persistent_path()
    if not path.exists():
        return {}
    logger.debug("Loading state from %s", path)
    with path.open("r") as f:
        state = json.load(f)
    path.unlink()
    return state


def save_persistent_state(data: bytes):
    path = get_persistent_path()
    with path.open("wb") as f:
        f.write(data)
