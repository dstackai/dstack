import logging
from contextlib import asynccontextmanager

import pydantic_core
from fastapi import FastAPI

import dstack.gateway.openai.store as openai_store
import dstack.gateway.version
from dstack.gateway.auth.routes import router as auth_router
from dstack.gateway.config.routes import router as config_router
from dstack.gateway.core.persistent import save_persistent_state
from dstack.gateway.core.store import get_store
from dstack.gateway.errors import GatewayError
from dstack.gateway.logging import configure_logging
from dstack.gateway.openai.routes import router as openai_router
from dstack.gateway.registry.routes import router as registry_router
from dstack.gateway.stats.collector import get_collector
from dstack.gateway.stats.routes import router as stats_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = get_store()
    openai = openai_store.get_store()
    stats_collector = get_collector()
    await store.subscribe(openai)
    await store.subscribe(stats_collector)
    yield

    async with store._lock, store.nginx._lock, openai._lock, stats_collector._lock:
        # Store the state between restarts
        save_persistent_state(
            pydantic_core.to_json(
                {
                    "store": store,
                    "openai": openai,
                    "stats_collector": stats_collector,
                }
            )
        )


configure_logging(logging.DEBUG)
app = FastAPI(lifespan=lifespan)
app.include_router(auth_router, prefix="/auth")
app.include_router(config_router, prefix="/api/config")
app.include_router(openai_router, prefix="/api/openai")
app.include_router(registry_router, prefix="/api/registry")
app.include_router(stats_router, prefix="/api/stats")


@app.get("/")
def get_info():
    return {"version": dstack.gateway.version.__version__}


@app.exception_handler(GatewayError)
async def gateway_error_handler(request, exc: GatewayError):
    return exc.to_response()
