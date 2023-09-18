import asyncio


async def run_async(func, *args):
    return await asyncio.get_running_loop().run_in_executor(None, func, *args)
