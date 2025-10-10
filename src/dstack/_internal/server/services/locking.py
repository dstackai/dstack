import asyncio
import collections.abc
import hashlib
from abc import abstractmethod
from asyncio import Lock
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Iterable, Iterator, Protocol, TypeVar, Union

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

KeyT = TypeVar("KeyT")


class LocksetLock(Protocol):
    async def acquire(self) -> bool: ...
    def release(self) -> None: ...
    async def __aenter__(self): ...
    async def __aexit__(self, exc_type, exc, tb): ...


T = TypeVar("T")


class Lockset(Protocol[T]):
    def __contains__(self, item: T, /) -> bool: ...
    def __iter__(self) -> Iterator[T]: ...
    def __len__(self) -> int: ...
    def add(self, item: T, /) -> None: ...
    def discard(self, item: T, /) -> None: ...
    def update(self, other: Iterable[T], /) -> None: ...
    def difference_update(self, other: Iterable[T], /) -> None: ...


class ResourceLocker:
    @abstractmethod
    def get_lockset(self, namespace: str) -> tuple[LocksetLock, Lockset]:
        """
        Returns a lockset containing locked resources for in-memory locking.
        Also returns a lock that guards the lockset.
        """
        pass

    @abstractmethod
    @asynccontextmanager
    async def lock_ctx(self, namespace: str, keys: list[KeyT]):
        """
        Acquires locks for all keys in namespace.
        The keys must be sorted to prevent deadlock.
        """
        yield


class InMemoryResourceLocker(ResourceLocker):
    def __init__(self):
        self.namespace_to_locks_map: dict[str, tuple[Lock, set]] = {}

    def get_lockset(self, namespace: str) -> tuple[Lock, set]:
        return self.namespace_to_locks_map.setdefault(namespace, (Lock(), set()))

    @asynccontextmanager
    async def lock_ctx(self, namespace: str, keys: list[KeyT]):
        lock, lockset = self.get_lockset(namespace)
        try:
            await _wait_to_lock_many(lock, lockset, keys)
            yield
        finally:
            lockset.difference_update(keys)


class DummyAsyncLock:
    async def __aenter__(self):
        pass

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def acquire(self):
        return True

    def release(self):
        pass


class DummySet(collections.abc.MutableSet):
    def __contains__(self, item):
        return False

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0

    def add(self, value):
        pass

    def discard(self, value):
        pass

    def update(self, other):
        pass

    def difference_update(self, other):
        pass


class DummyResourceLocker(ResourceLocker):
    def __init__(self):
        self.lock = DummyAsyncLock()
        self.lockset = DummySet()

    def get_lockset(self, namespace: str) -> tuple[DummyAsyncLock, DummySet]:
        return self.lock, self.lockset

    @asynccontextmanager
    async def lock_ctx(self, namespace: str, keys: list[KeyT]):
        yield


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


_in_memory_locker = InMemoryResourceLocker()
_dummy_locker = DummyResourceLocker()


def get_locker(dialect_name: str) -> ResourceLocker:
    if dialect_name == "sqlite":
        return _in_memory_locker
    # We could use an in-memory locker on Postgres
    # but it can lead to unnecessary lock contention,
    # so we use a dummy locker that does not take any locks.
    return _dummy_locker


async def _wait_to_lock_many(
    lock: asyncio.Lock, locked: set[KeyT], keys: list[KeyT], *, delay: float = 0.1
):
    """
    Retry locking until all the keys are locked.
    Lock is released during the sleep.
    The keys must be sorted to prevent deadlock.
    """
    left_to_lock = keys.copy()
    while True:
        async with lock:
            locked_now_num = 0
            for key in left_to_lock:
                if key in locked:
                    # Someone already acquired the lock, wait
                    break
                locked.add(key)
                locked_now_num += 1
            left_to_lock = left_to_lock[locked_now_num:]
        if not left_to_lock:
            return
        await asyncio.sleep(delay)
