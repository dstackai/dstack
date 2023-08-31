import csv
import io
import time
import urllib.request
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable

from dstack._internal.hub.utils.common import get_server_dir_path
from dstack._internal.utils.common import PathLike
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)
version_url = "https://dstack-gpu-pricing.s3.eu-west-1.amazonaws.com/v1/version"
catalog_url = "https://dstack-gpu-pricing.s3.eu-west-1.amazonaws.com/v1/{version}/catalog.zip"
update_interval = 60 * 60 * 4  # 4 hours


def get_catalog_path() -> Path:
    path = get_server_dir_path() / "data/catalog.zip"
    latest_version = get_latest_catalog_version(time_hash=round(time.time() / update_interval))
    if not path.exists() or get_catalog_version(path) < latest_version:
        logger.info("Downloading catalog %s...", latest_version)
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(catalog_url.format(version=latest_version), path)
    return path


def get_catalog_version(path: PathLike) -> str:
    with zipfile.ZipFile(path, "r") as zip_file:
        if "version" in zip_file.namelist():
            with zip_file.open("version", "r") as version_file:
                return version_file.read().decode("utf-8").strip()
    return "00000000"


@lru_cache()
def get_latest_catalog_version(time_hash: int = None) -> str:
    # lru_cache and time_hash are used as TTL
    with urllib.request.urlopen(version_url) as f:
        return f.read().decode("utf-8").strip()


def read_catalog_csv(filepath: str) -> Iterable[Dict[str, str]]:
    with zipfile.ZipFile(get_catalog_path(), "r") as zip_file:
        with zip_file.open(filepath, "r") as csv_file:
            reader: Iterable[Dict[str, str]] = csv.DictReader(io.TextIOWrapper(csv_file, "utf-8"))
            for row in reader:
                # Remove empty values
                yield {k: v for k, v in row.items() if v}
