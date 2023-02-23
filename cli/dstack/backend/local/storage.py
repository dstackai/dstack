import os
import shutil
from pathlib import Path
from typing import Callable, Dict, List, Optional

from dstack.backend.base.storage import Storage
from dstack.core.storage import StorageFile
from dstack.utils.common import removeprefix


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

    def list_files(self, dirpath: str) -> List[StorageFile]:
        full_dirpath = os.path.join(self.root_path, dirpath)
        files = []
        for dirpath, dirnames, filenames in os.walk(full_dirpath):
            for filename in filenames:
                full_filepath = os.path.join(dirpath, filename)
                filesize = os.stat(full_filepath, follow_symlinks=False).st_size
                filepath = removeprefix(full_filepath, full_dirpath)
                files.append(
                    StorageFile(
                        filepath=filepath,
                        filesize_in_bytes=filesize,
                    )
                )
        return files

    def download_file(self, source_path: str, dest_path: str, callback: Callable[[int], None]):
        full_source_path = os.path.join(self.root_path, source_path)
        shutil.copy2(full_source_path, dest_path)
        callback(os.path.getsize(dest_path))

    def upload_file(self, source_path: str, dest_path: str, callback: Callable[[int], None]):
        full_dest_path = os.path.join(self.root_path, dest_path)
        Path(full_dest_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, full_dest_path)
        callback(os.path.getsize(source_path))


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
