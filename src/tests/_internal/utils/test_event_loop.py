import asyncio

from dstack._internal.utils.event_loop import DaemonEventLoop


def test_daemon_event_loop():
    q = asyncio.Queue()

    async def worker(i):
        await q.put(i)

    async def all_workers():
        await asyncio.gather(*[worker(i) for i in range(3)])

    loop = DaemonEventLoop()
    loop.await_(all_workers())
    assert q.qsize() == 3
    assert {loop.await_(q.get()) for _ in range(3)} == {0, 1, 2}
