import functools

import sentry_sdk


def instrument_background_task(f):
    @functools.wraps(f)
    async def wrapper(*args, **kwargs):
        with sentry_sdk.start_transaction(name=f"background.{f.__name__}"):
            return await f(*args, **kwargs)

    return wrapper
