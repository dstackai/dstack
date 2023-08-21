import csv
import io
import urllib.request
import zipfile
from pathlib import Path
from typing import Dict, Iterable

from dstack._internal.hub.utils.common import get_server_dir_path

catalog_url = "https://dstack-gpu-pricing.s3.eu-west-1.amazonaws.com/v1/latest/catalog.zip"


def get_catalog_path() -> Path:
    path = get_server_dir_path() / "data/catalog.zip"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(catalog_url, path)
    return path


def read_catalog_csv(filepath: str) -> Iterable[Dict[str, str]]:
    with zipfile.ZipFile(get_catalog_path(), "r") as zip_file:
        with zip_file.open(filepath, "r") as csv_file:
            reader: Iterable[Dict[str, str]] = csv.DictReader(io.TextIOWrapper(csv_file, "utf-8"))
            for row in reader:
                yield {k: v for k, v in row.items() if v}
