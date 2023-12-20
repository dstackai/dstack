import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

import dstack.gateway.openai.store as openai_store
import dstack.gateway.version
from dstack.gateway.logging import configure_logging
from dstack.gateway.openai.routes import router as openai_router
from dstack.gateway.registry.routes import router as registry_router
from dstack.gateway.services.store import get_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = get_store()
    await store.subscribe(openai_store.get_store())
    yield
    await store.unregister_all()


configure_logging(logging.DEBUG)
app = FastAPI(lifespan=lifespan)
app.include_router(registry_router, prefix="/api/registry")
app.include_router(openai_router, prefix="/api/openai")


@app.get("/")
def get_info():
    return {"version": dstack.gateway.version.__version__}
