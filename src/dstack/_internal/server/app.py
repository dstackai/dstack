import time
from contextlib import asynccontextmanager
from typing import Callable
from urllib.parse import urlparse

import sentry_sdk
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

import dstack.version
from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.services.configs import create_default_project_config
from dstack._internal.server import settings
from dstack._internal.server.background import start_background_tasks
from dstack._internal.server.db import get_session, get_session_ctx, migrate
from dstack._internal.server.routers import (
    backends,
    gateways,
    logs,
    projects,
    repos,
    runs,
    secrets,
    users,
)
from dstack._internal.server.services.config import ServerConfigManager
from dstack._internal.server.services.projects import get_or_create_default_project
from dstack._internal.server.services.storage import init_default_storage
from dstack._internal.server.services.users import get_or_create_admin_user
from dstack._internal.server.settings import DEFAULT_PROJECT_NAME, SERVER_URL
from dstack._internal.server.utils.logging import configure_logging
from dstack._internal.server.utils.routers import get_server_client_error_details
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


def create_app() -> FastAPI:

    if settings.SENTRY_DSN is not None:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.SERVER_ENVIRONMENT,
            enable_tracing=True,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        )

    app = FastAPI(docs_url="/api/docs", lifespan=lifespan)
    return app


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    await migrate()
    async with get_session_ctx() as session:
        admin, _ = await get_or_create_admin_user(session=session)
        default_project, porject_created = await get_or_create_default_project(
            session=session, user=admin
        )
        if settings.SERVER_CONFIG_ENABLED:
            server_config_manager = ServerConfigManager()
            print("Reading project configurations from ~/.dstack/server/config.yml...")
            config_loaded = server_config_manager.load_config()
            if not config_loaded:
                print("No config was found. Initializing default configuration...")
                await server_config_manager.init_config(session=session)
            else:
                print("Applying configuration...")
                await server_config_manager.apply_config(session=session)
    create_default_project_config(
        project_name=DEFAULT_PROJECT_NAME, url=SERVER_URL, token=admin.token
    )
    if settings.SERVER_BUCKET is not None:
        init_default_storage()
    scheduler = start_background_tasks()
    dstack_version = dstack.version.__version__ if dstack.version.__version__ else "(no version)"
    print(f"\nThe dstack server {dstack_version} is running at {SERVER_URL}.")
    print(f"The admin user token is '{admin.token}'.")
    for func in _ON_STARTUP_HOOKS:
        await func(app)
    yield
    scheduler.shutdown()


_ON_STARTUP_HOOKS = []


def register_on_startup_hook(func: Callable[[FastAPI], None]):
    _ON_STARTUP_HOOKS.append(func)


def register_routes(app: FastAPI):
    app.include_router(users.router)
    app.include_router(projects.router)
    app.include_router(backends.root_router)
    app.include_router(backends.project_router)
    app.include_router(repos.router)
    app.include_router(runs.root_router)
    app.include_router(runs.project_router)
    app.include_router(logs.router)
    app.include_router(secrets.router)
    app.include_router(gateways.router)

    @app.exception_handler(ServerClientError)
    async def server_client_error_handler(request: Request, exc: ServerClientError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": get_server_client_error_details(exc)},
        )

    @app.middleware("http")
    async def log_request(request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.debug(
            "Processed request %s %s in %s", request.method, request.url, f"{process_time:0.6f}s"
        )
        return response

    @app.get("/healthcheck")
    async def healthcheck():
        return JSONResponse(content={"status": "running"})

    @app.get("/")
    async def index():
        return RedirectResponse("/api/docs")
