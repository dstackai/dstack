from typing import List, Type

from dstack._internal.backend.base.storage import Storage
from dstack._internal.core.head import BaseHead, T


def put_head_object(storage: Storage, head: BaseHead) -> str:
    key = head.encode()
    storage.put_object(key, content="")
    return key


def list_head_objects(storage: Storage, cls: Type[T]) -> List[T]:
    keys = storage.list_objects(cls.prefix())
    return [cls.decode(key) for key in keys]


def delete_head_object(storage, head: BaseHead):
    storage.delete_object(head.encode())
