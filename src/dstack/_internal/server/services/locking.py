import asyncio
from asyncio import Lock
from typing import Dict, List, Set, Tuple, TypeVar


class DBLocker:
    def __init__(self):
        self.namespace_to_locks_map: Dict[str, Tuple[Lock, set]] = {}

    def get_lock_and_lockset(self, namespace: str) -> Tuple[Lock, set]:
        return self.namespace_to_locks_map.setdefault(namespace, (Lock(), set()))


KeyT = TypeVar("KeyT")


async def wait_to_lock(lock: asyncio.Lock, locked: Set[KeyT], key: KeyT, *, delay: float = 0.1):
    """
    Retry locking until the key is locked.
    Lock is released during the sleep.
    """
    while True:
        async with lock:
            if key not in locked:
                locked.add(key)
                return
        await asyncio.sleep(delay)


async def wait_to_lock_many(
    lock: asyncio.Lock, locked: Set[KeyT], keys: List[KeyT], *, delay: float = 0.1
):
    """
    Retry locking until all the keys are locked.
    Lock is released during the sleep.
    The keys must be sorted to prevent deadlock.
    """
    left_to_lock = keys.copy()
    while len(left_to_lock) > 0:
        async with lock:
            for key in left_to_lock:
                if key not in locked:
                    locked.add(key)
                    left_to_lock.remove(key)
        await asyncio.sleep(delay)


db_locker = DBLocker()
