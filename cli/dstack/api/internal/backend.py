from typing import Optional

from dstack.backend.aws import AwsBackend
from dstack.backend.gcp import GCPBackend
from dstack.backend.local import LocalBackend

backends_classes = [AwsBackend, GCPBackend, LocalBackend]

backend_name_to_backend_class_map = {b.NAME: b for b in backends_classes}


def get_backend_class(backend_name: str) -> Optional[type]:
    return backend_name_to_backend_class_map.get(backend_name)
