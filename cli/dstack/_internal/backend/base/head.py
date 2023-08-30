from typing import List, Tuple, Type, Union

from dstack._internal.backend.base.storage import Storage
from dstack._internal.core.head import BaseHead, T


def put_head_object(storage: Storage, head: BaseHead) -> str:
    key = head.encode()
    storage.put_object(key, content="")
    return key


def replace_head_object(storage: Storage, old_key: str, new_head: BaseHead) -> str:
    storage.delete_object(old_key)
    return put_head_object(storage, new_head)


def list_head_objects(
    storage: Storage, cls: Type[T], include_key: bool = False
) -> List[Union[T, Tuple[str, T]]]:
    keys = storage.list_objects(cls.prefix())
    if include_key:
        return [(key, cls.decode(key)) for key in keys]
    return [cls.decode(key) for key in keys]


def delete_head_object(storage, head: BaseHead):
    storage.delete_object(head.encode())
