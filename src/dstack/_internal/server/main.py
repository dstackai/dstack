from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

import dstack.version
from dstack._internal.core.services.configs import create_default_project_config
from dstack._internal.server.background import start_background_tasks
from dstack._internal.server.db import get_session, get_session_ctx, migrate
from dstack._internal.server.routers import backends, logs, projects, repos, runs, secrets, users
from dstack._internal.server.services.projects import (
    DEFAULT_PROJECT_NAME,
    get_or_create_default_project,
)
from dstack._internal.server.services.users import get_or_create_admin_user
from dstack._internal.server.settings import SERVER_URL
from dstack._internal.server.utils.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    await migrate()
    async with get_session_ctx() as session:
        admin, _ = await get_or_create_admin_user(session=session)
        default_project, created = await get_or_create_default_project(session=session, user=admin)
    create_default_project_config(
        project_name=DEFAULT_PROJECT_NAME, url=SERVER_URL, token=admin.token
    )
    scheduler = start_background_tasks()
    url = f"{SERVER_URL}?token={admin.token}"
    dstack_version = dstack.version.__version__ if dstack.version.__version__ else "(no version)"
    print(f"\nThe dstack server {dstack_version} is running at:\n{url}")
    yield
    scheduler.shutdown()


app = FastAPI(docs_url="/api/docs", lifespan=lifespan)
app.include_router(users.router)
app.include_router(projects.router)
app.include_router(backends.root_router)
app.include_router(backends.project_router)
app.include_router(repos.router)
app.include_router(runs.router)
app.include_router(logs.router)
app.include_router(secrets.router)
