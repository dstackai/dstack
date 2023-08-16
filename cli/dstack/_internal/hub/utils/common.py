import asyncio
import os
from pathlib import Path


def get_server_dir_path() -> Path:
    return os.getenv("DSTACK_SERVER_DIR") or Path.home() / ".dstack" / "server"


async def run_async(func, *args):
    return await asyncio.get_running_loop().run_in_executor(None, func, *args)
