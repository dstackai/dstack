from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.server.services.locking import advisory_lock_ctx, try_advisory_lock_ctx


class _Result:
    def __init__(self, value: bool) -> None:
        self._value = value

    def scalar_one(self) -> bool:
        return self._value


class _ReleaseFailsBind:
    """Acquires the lock successfully, then fails to release it."""

    def __init__(self, locked: bool = True) -> None:
        self._locked = locked
        self.executes = 0

    async def execute(self, statement: Any) -> _Result:
        self.executes += 1
        if self.executes > 1:
            raise RuntimeError("connection invalidated")
        return _Result(self._locked)


def _bind(locked: bool = True) -> tuple[_ReleaseFailsBind, AsyncSession]:
    bind = _ReleaseFailsBind(locked)
    return bind, cast(AsyncSession, bind)


@pytest.mark.asyncio
class TestAdvisoryLockCtx:
    async def test_tolerates_release_failure(self):
        bind, session = _bind()

        async with advisory_lock_ctx(
            bind=session, dialect_name="postgresql", resource="test_resource"
        ):
            pass

        assert bind.executes == 2

    async def test_release_failure_does_not_mask_error(self):
        bind, session = _bind()

        with pytest.raises(ValueError, match="failed inside the lock"):
            async with advisory_lock_ctx(
                bind=session, dialect_name="postgresql", resource="test_resource"
            ):
                raise ValueError("failed inside the lock")

        assert bind.executes == 2


@pytest.mark.asyncio
class TestTryAdvisoryLockCtx:
    async def test_tolerates_release_failure(self):
        bind, session = _bind()

        async with try_advisory_lock_ctx(
            bind=session, dialect_name="postgresql", resource="test_resource"
        ) as locked:
            assert locked

        assert bind.executes == 2

    async def test_release_failure_does_not_mask_error(self):
        bind, session = _bind()

        with pytest.raises(ValueError, match="failed inside the lock"):
            async with try_advisory_lock_ctx(
                bind=session, dialect_name="postgresql", resource="test_resource"
            ):
                raise ValueError("failed inside the lock")

        assert bind.executes == 2

    async def test_does_not_release_when_lock_not_acquired(self):
        bind, session = _bind(locked=False)

        async with try_advisory_lock_ctx(
            bind=session, dialect_name="postgresql", resource="test_resource"
        ) as locked:
            assert not locked

        assert bind.executes == 1
