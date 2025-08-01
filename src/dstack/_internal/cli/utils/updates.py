import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from packaging import version as pkg_version

from dstack import version
from dstack._internal.cli.utils.common import console
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


def anonymous_installation_id() -> str:
    ai_id_path = Path.home() / ".cache" / ".dstack" / "anonymous_installation_id"
    if not ai_id_path.exists():
        ai_id_path.parent.mkdir(parents=True, exist_ok=True)
        with open(ai_id_path, "w") as f:
            ai_id = uuid.uuid4().hex
            f.write(ai_id)
    else:
        with open(ai_id_path, "r") as f:
            ai_id = f.readline().strip()
    return ai_id


def get_latest_version() -> Optional[str]:
    latest_version_url = f"https://get.dstack.ai/{_get_channel()}/latest-version"
    try:
        response = requests.get(
            latest_version_url,
            params={
                "anonymous_installation_id": anonymous_installation_id(),
                "version": version.__version__,
            },
            timeout=5,
        )
        if response.status_code == 200:
            return response.text.strip()
        else:
            return None
    except Exception:
        return None


def _is_last_check_time_outdated() -> bool:
    path = _get_last_check_path()
    if not path.exists():
        return True
    current_datetime = datetime.now()
    modified_datetime = datetime.fromtimestamp(path.stat().st_mtime)
    return (
        modified_datetime.timetuple().tm_yday != current_datetime.timetuple().tm_yday
        or modified_datetime.year != current_datetime.year
    )


def is_update_available(current_version: str, latest_version: str) -> bool:
    """
    Return True if latest_version is newer than current_version.
    Pre-releases are only considered if the current version is also a pre-release.
    """
    _current_version = pkg_version.parse(str(current_version))
    _latest_version = pkg_version.parse(str(latest_version))
    return _current_version < _latest_version and (
        not _latest_version.is_prerelease or _current_version.is_prerelease
    )


def _check_version():
    latest_version = get_latest_version()
    if latest_version is not None:
        if is_update_available(version.__version__, latest_version):
            console.print(f"A new version of dstack is available: [code]{latest_version}[/]\n")


def _update_last_check_time():
    path = _get_last_check_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


def _get_channel() -> str:
    return "cli" if version.__is_release__ else "stgn-cli"


def _get_last_check_path() -> Path:
    return Path.home() / ".cache" / ".dstack" / _get_channel() / "last_check"


def check_for_updates():
    if version.__is_release__:
        if _is_last_check_time_outdated():
            logger.debug("Checking for updates...")
            _check_version()
            _update_last_check_time()
