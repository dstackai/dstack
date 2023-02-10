import os
from pathlib import Path
from typing import Dict, List, Optional

from dstack.backend.base.storage import Storage


class LocalStorage(Storage):
    def __init__(self, root_path: str):
        self.root_path = root_path

    def put_object(self, key: str, content: str, metadata: Optional[Dict] = None):
        _put_object(
            Root=self.root_path,
            Key=key,
            Body=content,
        )

    def get_object(self, key: str) -> Optional[str]:
        try:
            return _get_object(
                Root=self.root_path,
                Key=key,
            )
        except IOError:
            return None

    def delete_object(self, key: str):
        return _delete_object(
            Root=self.root_path,
            Key=key,
        )

    def list_objects(self, keys_prefix: str) -> List[str]:
        return _list_objects(
            Root=self.root_path,
            Prefix=keys_prefix,
        )


def _list_objects(Root: str, Prefix: str, MaxKeys: Optional[int] = None) -> List[str]:
    prefix_path = Path.joinpath(Root, Prefix)
    parent_dir = prefix_path.parent
    file_prefix = prefix_path.name
    if not os.path.exists(parent_dir):
        return []
    l = []
    count_keys = 0
    for file in os.listdir(parent_dir):
        if file.startswith(file_prefix):
            if MaxKeys:
                if count_keys == MaxKeys:
                    break
            l.append(str(Path(parent_dir, file).relative_to(Root)))
            count_keys += 1
    return l


def _put_object(Root: str, Key: str, Body: str):
    filepath = os.path.join(Root, Key)
    Path(filepath).parent.mkdir(exist_ok=True, parents=True)
    with open(filepath, "w+") as f:
        f.write(Body)


def _get_object(Root: str, Key: str):
    if not os.path.exists(Root):
        raise IOError()
    if not os.path.exists(os.path.join(Root, Key)):
        raise IOError()
    with open(os.path.join(Root, Key)) as f:
        body = f.read()
    return body or ""


def _delete_object(Root: str, Key: str):
    if not os.path.exists(Root):
        return
    path = os.path.join(Root, Key)
    if os.path.exists(path):
        os.remove(path)


def _list_all_objects(Root: str, Prefix: str):
    if not os.path.exists(Root):
        return []
    files = os.listdir(Root)
    list_dir = []
    for file in files:
        if file.startswith(Prefix) and os.path.isdir(os.path.join(Root, file)):
            list_dir.append(file)
    for _dir in list_dir:
        job_dir = os.path.join(Root, _dir)
        for root, sub_dirs, files in os.walk(job_dir):
            clear_root = Path(root).relative_to(job_dir)
            for filename in files:
                file_path = os.path.join(clear_root, filename)
                file_size = os.path.getsize(os.path.join(root, filename))
                yield _dir, file_path, file_size
