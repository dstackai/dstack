import os
import time
from contextlib import asynccontextmanager
from typing import Awaitable, Callable, List

import sentry_sdk
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from dstack._internal.cli.utils.common import console
from dstack._internal.core.errors import ForbiddenError, ServerClientError
from dstack._internal.core.services.configs import update_default_project
from dstack._internal.server import settings
from dstack._internal.server.background import start_background_tasks
from dstack._internal.server.db import get_session_ctx, migrate
from dstack._internal.server.routers import (
    backends,
    gateways,
    logs,
    pools,
    projects,
    repos,
    runs,
    secrets,
    users,
    volumes,
)
from dstack._internal.server.services.config import ServerConfigManager
from dstack._internal.server.services.gateways import gateway_connections_pool, init_gateways
from dstack._internal.server.services.projects import get_or_create_default_project
from dstack._internal.server.services.storage import init_default_storage
from dstack._internal.server.services.users import get_or_create_admin_user
from dstack._internal.server.settings import (
    DEFAULT_PROJECT_NAME,
    DO_NOT_UPDATE_DEFAULT_PROJECT,
    SERVER_CONFIG_FILE_PATH,
    SERVER_URL,
    UPDATE_DEFAULT_PROJECT,
)
from dstack._internal.server.utils.logging import configure_logging
from dstack._internal.server.utils.routers import (
    check_client_server_compatibility,
    error_detail,
    get_server_client_error_details,
)
from dstack._internal.settings import DSTACK_VERSION
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.ssh import check_required_ssh_version

logger = get_logger(__name__)


def create_app() -> FastAPI:
    if settings.SENTRY_DSN is not None:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            release=DSTACK_VERSION,
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
        console.print(
            """[purple]╱╱╭╮╱╱╭╮╱╱╱╱╱╱╭╮
╱╱┃┃╱╭╯╰╮╱╱╱╱╱┃┃
╭━╯┣━┻╮╭╋━━┳━━┫┃╭╮
┃╭╮┃━━┫┃┃╭╮┃╭━┫╰╯╯
┃╰╯┣━━┃╰┫╭╮┃╰━┫╭╮╮
╰━━┻━━┻━┻╯╰┻━━┻╯╰╯
╭━━┳━━┳━┳╮╭┳━━┳━╮
┃━━┫┃━┫╭┫╰╯┃┃━┫╭╯
┣━━┃┃━┫┃╰╮╭┫┃━┫┃
╰━━┻━━┻╯╱╰╯╰━━┻╯
[/]"""
        )
        admin, _ = await get_or_create_admin_user(session=session)
        default_project, project_created = await get_or_create_default_project(
            session=session, user=admin
        )
        if not check_required_ssh_version():
            logger.warning("OpenSSH 8.4+ is required. The dstack server may not work properly")
        if settings.SERVER_CONFIG_ENABLED:
            server_config_manager = ServerConfigManager()
            config_loaded = server_config_manager.load_config()
            server_config_dir = str(SERVER_CONFIG_FILE_PATH).replace(
                os.path.expanduser("~"), "~", 1
            )
            if not config_loaded:
                logger.info("Initializing the default configuration...", {"show_path": False})
                await server_config_manager.init_config(session=session)
                logger.info(
                    f"Initialized the default configuration at [link=file://{SERVER_CONFIG_FILE_PATH}]{server_config_dir}[/link]",
                    {"show_path": False},
                )
            else:
                logger.info(
                    f"Applying [link=file://{SERVER_CONFIG_FILE_PATH}]{server_config_dir}[/link]...",
                    {"show_path": False},
                )

                await server_config_manager.apply_config(session=session, owner=admin)
        await init_gateways(session=session)
    update_default_project(
        project_name=DEFAULT_PROJECT_NAME,
        url=SERVER_URL,
        token=admin.token,
        default=UPDATE_DEFAULT_PROJECT,
        no_default=DO_NOT_UPDATE_DEFAULT_PROJECT,
    )
    if settings.SERVER_BUCKET is not None:
        init_default_storage()
    scheduler = start_background_tasks()
    dstack_version = DSTACK_VERSION if DSTACK_VERSION else "(no version)"
    logger.info(f"The admin token is {admin.token}", {"show_path": False})
    logger.info(
        f"The dstack server {dstack_version} is running at {SERVER_URL}",
        {"show_path": False},
    )
    for func in _ON_STARTUP_HOOKS:
        await func(app)
    yield
    scheduler.shutdown()
    await gateway_connections_pool.remove_all()


_ON_STARTUP_HOOKS = []


def register_on_startup_hook(func: Callable[[FastAPI], Awaitable[None]]):
    _ON_STARTUP_HOOKS.append(func)


_NO_API_VERSION_CHECK_ROUTES = ["/api/docs"]


def add_no_api_version_check_routes(paths: List[str]):
    _NO_API_VERSION_CHECK_ROUTES.extend(paths)


def register_routes(app: FastAPI):
    app.include_router(users.router)
    app.include_router(projects.router)
    app.include_router(pools.root_router)
    app.include_router(pools.router)
    app.include_router(backends.root_router)
    app.include_router(backends.project_router)
    app.include_router(repos.router)
    app.include_router(runs.root_router)
    app.include_router(runs.project_router)
    app.include_router(logs.router)
    app.include_router(secrets.router)
    app.include_router(gateways.router)
    app.include_router(volumes.router)

    @app.exception_handler(ForbiddenError)
    async def forbidden_error_handler(request: Request, exc: ForbiddenError):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=error_detail("Access denied"),
        )

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

    @app.middleware("http")
    async def check_client_version(request: Request, call_next):
        if (
            not request.url.path.startswith("/api/")
            or request.url.path in _NO_API_VERSION_CHECK_ROUTES
        ):
            return await call_next(request)
        response = check_client_server_compatibility(
            client_version=request.headers.get("x-api-version"),
            server_version=DSTACK_VERSION,
        )
        if response is not None:
            return response
        return await call_next(request)

    @app.get("/healthcheck")
    async def healthcheck():
        return JSONResponse(content={"status": "running"})

    @app.get("/")
    async def index():
        return RedirectResponse("/api/docs")
