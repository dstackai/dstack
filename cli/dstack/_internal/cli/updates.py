import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from packaging import version as pkg_version

from dstack import version


def anonymous_installation_id() -> str:
    ai_id_path = Path.home() / ".cache" / ".dstack" / "anonymous_installation_id"
    if not ai_id_path.exists():
        ai_id_path.parent.mkdir(parents=True, exist_ok=True)
        with open(ai_id_path, "w") as f:
            ai_id = uuid.uuid4().hex
            f.write(ai_id)
    else:
        with open(ai_id_path) as f:
            ai_id = f.readline().strip()
    return ai_id


def get_latest_version() -> Optional[str]:
    latest_version_url = (
        f"https://get.dstack.ai"
        f"/{'cli' if version.__is_release__ else 'stgn-cli'}"
        f"/latest-version"
    )
    try:
        response = requests.get(
            latest_version_url,
            params={
                "anonymous_installation_id": anonymous_installation_id(),
                "version": version.__version__,
            },
        )
        if response.status_code == 200:
            return response.text.strip()
        else:
            return None
    except Exception:
        return None


def _is_last_check_time_outdated(last_check_path) -> bool:
    modified_datetime = datetime.fromtimestamp(os.stat(last_check_path).st_mtime)
    current_datetime = datetime.now()
    return (
        modified_datetime.timetuple().tm_yday != current_datetime.timetuple().tm_yday
        or modified_datetime.year != current_datetime.year
    )


def _check_version():
    latest_version = get_latest_version()
    if latest_version is not None:
        if pkg_version.parse(str(version.__version__)) < pkg_version.parse(latest_version):
            print(f"A new version of dstack is available: {latest_version}\n")


def _update_last_check_time(last_check_path):
    if last_check_path.exists():
        now_time = datetime.now().timestamp()
        os.utime(last_check_path, (now_time, now_time))
    else:
        last_check_path.parent.mkdir(parents=True, exist_ok=True)
        open(last_check_path, "a").close()


def check_for_updates():
    current_version = version.__version__
    if current_version:
        last_check_path = (
            Path.home()
            / ".cache"
            / ".dstack"
            / ("cli" if version.__is_release__ else "stgn-cli")
            / "last_check"
        )

        if not last_check_path.exists() or _is_last_check_time_outdated(last_check_path):
            _check_version()
            _update_last_check_time(last_check_path)
