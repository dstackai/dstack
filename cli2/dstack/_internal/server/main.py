from contextlib import asynccontextmanager

from fastapi import FastAPI

from dstack._internal.server.routers import logs, repos, runs, secrets


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(docs_url="/api/docs", lifespan=lifespan)
app.include_router(repos.router)
app.include_router(runs.router)
app.include_router(logs.router)
app.include_router(secrets.router)
