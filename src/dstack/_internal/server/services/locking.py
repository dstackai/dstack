import asyncio
import hashlib
from asyncio import Lock
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, List, Set, Tuple, TypeVar, Union

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

KeyT = TypeVar("KeyT")


class ResourceLocker:
    def __init__(self):
        self.namespace_to_locks_map: Dict[str, Tuple[Lock, set]] = {}

    def get_lockset(self, namespace: str) -> Tuple[Lock, set]:
        """
        Returns a lockset containing locked resources for in-memory locking.
        Also returns a lock that guards the lockset.
        """
        return self.namespace_to_locks_map.setdefault(namespace, (Lock(), set()))

    @asynccontextmanager
    async def lock_ctx(self, namespace: str, keys: List[KeyT]):
        """
        Acquires locks for all keys in namespace.
        The keys must be sorted to prevent deadlock.
        """
        lock, lockset = self.get_lockset(namespace)
        try:
            await _wait_to_lock_many(lock, lockset, keys)
            yield
        finally:
            lockset.difference_update(keys)


def string_to_lock_id(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest(), 16) % (2**63)


@asynccontextmanager
async def advisory_lock_ctx(
    bind: Union[AsyncConnection, AsyncSession], dialect_name: str, resource: str
):
    if dialect_name == "postgresql":
        await bind.execute(select(func.pg_advisory_lock(string_to_lock_id(resource))))
    try:
        yield
    finally:
        if dialect_name == "postgresql":
            await bind.execute(select(func.pg_advisory_unlock(string_to_lock_id(resource))))


@asynccontextmanager
async def try_advisory_lock_ctx(
    bind: Union[AsyncConnection, AsyncSession], dialect_name: str, resource: str
) -> AsyncGenerator[bool, None]:
    locked = True
    if dialect_name == "postgresql":
        res = await bind.execute(select(func.pg_try_advisory_lock(string_to_lock_id(resource))))
        locked = res.scalar_one()
    try:
        yield locked
    finally:
        if dialect_name == "postgresql" and locked:
            await bind.execute(select(func.pg_advisory_unlock(string_to_lock_id(resource))))


_locker = ResourceLocker()


def get_locker() -> ResourceLocker:
    return _locker


async def _wait_to_lock_many(
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
            locked_now_num = 0
            for key in left_to_lock:
                if key in locked:
                    # Someone already aquired the lock, wait
                    break
                locked.add(key)
                locked_now_num += 1
            left_to_lock = left_to_lock[locked_now_num:]
        await asyncio.sleep(delay)
