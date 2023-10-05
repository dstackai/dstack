import csv
import io
import logging
import time
import urllib.request
import zipfile
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from filelock import FileLock
from pydantic import BaseModel, Field
from typing_extensions import Annotated

from dstack._internal.server.settings import SERVER_DATA_DIR_PATH
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import PathLike

logger = get_logger(__name__)
version_url = "https://dstack-gpu-pricing.s3.eu-west-1.amazonaws.com/v1/version"
catalog_url = "https://dstack-gpu-pricing.s3.eu-west-1.amazonaws.com/v1/{version}/catalog.zip"
update_interval = 60 * 60 * 4  # 4 hours


class CatalogItem(BaseModel):
    provider: str
    instance_name: str
    location: str
    price: float
    cpus: Annotated[int, Field(alias="cpu")]
    memory: float
    gpu_count: int
    gpu_name: Optional[str]
    gpu_memory: Optional[float]
    spot: bool


@lru_cache()
def get_latest_catalog_version(time_hash: int = None) -> str:
    # lru_cache and time_hash are used as TTL
    with urllib.request.urlopen(version_url) as f:
        return f.read().decode("utf-8").strip()


def get_catalog_version(path: PathLike) -> str:
    with zipfile.ZipFile(path, "r") as zip_file:
        if "version" in zip_file.namelist():
            with zip_file.open("version", "r") as version_file:
                return version_file.read().decode("utf-8").strip()
    return "00000000"


@contextmanager
def open_catalog(path: PathLike) -> zipfile.ZipFile:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    latest_version = get_latest_catalog_version(time_hash=round(time.time() / update_interval))

    with FileLock(str(path) + ".lock"):
        if not path.exists() or get_catalog_version(path) < latest_version:
            logger.info("Downloading catalog %s...", latest_version)
            path.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(catalog_url.format(version=latest_version), path)
        with zipfile.ZipFile(path, "r") as zip_file:
            yield zip_file


# todo replace with gpuhunt.query
def query(provider: str) -> List[CatalogItem]:
    items = []
    with open_catalog(SERVER_DATA_DIR_PATH / "catalog.zip") as zip_file:
        with zip_file.open(f"{provider}.csv", "r") as csv_file:
            reader: Iterable[Dict[str, str]] = csv.DictReader(io.TextIOWrapper(csv_file, "utf-8"))
            for item in reader:
                item["provider"] = provider
                items.append(CatalogItem.parse_obj(remove_empty_values(item)))
    return items


def remove_empty_values(obj: dict) -> dict:
    return {k: v for k, v in obj.items() if v}
