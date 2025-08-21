import asyncio
import importlib.resources
import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Awaitable, Callable, List

import sentry_sdk
from fastapi import FastAPI, Request, Response, status
from fastapi.datastructures import URL
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import Counter, Histogram
from sentry_sdk.types import SamplingContext

from dstack._internal.cli.utils.common import console
from dstack._internal.core.errors import ForbiddenError, ServerClientError
from dstack._internal.core.services.configs import update_default_project
from dstack._internal.proxy.lib.deps import get_injector_from_app
from dstack._internal.proxy.lib.routers import model_proxy
from dstack._internal.server import settings
from dstack._internal.server.background import start_background_tasks
from dstack._internal.server.background.tasks.process_probes import PROBES_SCHEDULER
from dstack._internal.server.db import get_db, get_session_ctx, migrate
from dstack._internal.server.routers import (
    backends,
    files,
    fleets,
    gateways,
    gpus,
    instances,
    logs,
    metrics,
    projects,
    prometheus,
    repos,
    runs,
    secrets,
    server,
    users,
    volumes,
)
from dstack._internal.server.services.config import ServerConfigManager
from dstack._internal.server.services.gateways import gateway_connections_pool, init_gateways
from dstack._internal.server.services.locking import advisory_lock_ctx
from dstack._internal.server.services.projects import get_or_create_default_project
from dstack._internal.server.services.proxy.deps import ServerProxyDependencyInjector
from dstack._internal.server.services.proxy.routers import service_proxy
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
    CustomORJSONResponse,
    check_client_server_compatibility,
    error_detail,
    get_server_client_error_details,
)
from dstack._internal.settings import DSTACK_VERSION
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.ssh import check_required_ssh_version

logger = get_logger(__name__)

# Server HTTP metrics
REQUESTS_TOTAL = Counter(
    "dstack_server_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "http_status", "project_name"],
)
REQUEST_DURATION = Histogram(
    "dstack_server_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint", "http_status", "project_name"],
)


def create_app() -> FastAPI:
    app = FastAPI(
        docs_url="/api/docs",
        lifespan=lifespan,
    )
    app.state.proxy_dependency_injector = ServerProxyDependencyInjector()
    return app


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    if settings.SENTRY_DSN is not None:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            release=DSTACK_VERSION,
            environment=settings.SERVER_ENVIRONMENT,
            enable_tracing=True,
            traces_sampler=_sentry_traces_sampler,
            profiles_sample_rate=settings.SENTRY_PROFILES_SAMPLE_RATE,
        )
    server_executor = ThreadPoolExecutor(max_workers=settings.SERVER_EXECUTOR_MAX_WORKERS)
    asyncio.get_running_loop().set_default_executor(server_executor)
    await migrate()
    _print_dstack_logo()
    if not check_required_ssh_version():
        logger.warning("OpenSSH 8.4+ is required. The dstack server may not work properly")
    server_config_manager = None
    server_config_loaded = False
    if settings.SERVER_CONFIG_ENABLED:
        server_config_manager = ServerConfigManager()
        server_config_loaded = server_config_manager.load_config()
        # Encryption has to be configured before working with users and projects
        await server_config_manager.apply_encryption()
    async with get_session_ctx() as session:
        async with advisory_lock_ctx(
            bind=session,
            dialect_name=get_db().dialect_name,
            resource="server_init",
        ):
            admin, _ = await get_or_create_admin_user(session=session)
            await get_or_create_default_project(
                session=session,
                user=admin,
            )
            if server_config_manager is not None:
                server_config_dir = _get_server_config_dir()
                if not server_config_loaded:
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
        token=admin.token.get_plaintext_or_error(),
        yes=UPDATE_DEFAULT_PROJECT,
        no=DO_NOT_UPDATE_DEFAULT_PROJECT,
    )
    if settings.SERVER_S3_BUCKET is not None or settings.SERVER_GCS_BUCKET is not None:
        init_default_storage()
    scheduler = None
    if settings.SERVER_BACKGROUND_PROCESSING_ENABLED:
        scheduler = start_background_tasks()
    else:
        logger.info("Background processing is disabled")
    PROBES_SCHEDULER.start()
    dstack_version = DSTACK_VERSION if DSTACK_VERSION else "(no version)"
    logger.info(f"The admin token is {admin.token.get_plaintext_or_error()}", {"show_path": False})
    logger.info(
        f"The dstack server {dstack_version} is running at {SERVER_URL}",
        {"show_path": False},
    )
    for func in _ON_STARTUP_HOOKS:
        await func(app)
    yield
    if scheduler is not None:
        scheduler.shutdown()
    PROBES_SCHEDULER.shutdown(wait=False)
    await gateway_connections_pool.remove_all()
    service_conn_pool = await get_injector_from_app(app).get_service_connection_pool()
    await service_conn_pool.remove_all()
    await get_db().engine.dispose()
    # Let checked-out DB connections close as dispose() only closes checked-in connections
    await asyncio.sleep(3)


_ON_STARTUP_HOOKS = []


def register_on_startup_hook(func: Callable[[FastAPI], Awaitable[None]]):
    _ON_STARTUP_HOOKS.append(func)


_NO_API_VERSION_CHECK_ROUTES = ["/api/docs"]


def add_no_api_version_check_routes(paths: List[str]):
    _NO_API_VERSION_CHECK_ROUTES.extend(paths)


def register_routes(app: FastAPI, ui: bool = True):
    app.include_router(server.router)
    app.include_router(users.router)
    app.include_router(projects.router)
    app.include_router(backends.root_router)
    app.include_router(backends.project_router)
    app.include_router(fleets.root_router)
    app.include_router(fleets.project_router)
    app.include_router(instances.root_router)
    app.include_router(instances.project_router)
    app.include_router(repos.router)
    app.include_router(runs.root_router)
    app.include_router(runs.project_router)
    app.include_router(gpus.project_router)
    app.include_router(metrics.router)
    app.include_router(logs.router)
    app.include_router(secrets.router)
    app.include_router(gateways.router)
    app.include_router(volumes.root_router)
    app.include_router(volumes.project_router)
    app.include_router(service_proxy.router, prefix="/proxy/services", tags=["service-proxy"])
    app.include_router(model_proxy.router, prefix="/proxy/models", tags=["model-proxy"])
    app.include_router(prometheus.router)
    app.include_router(files.router)

    @app.exception_handler(ForbiddenError)
    async def forbidden_error_handler(request: Request, exc: ForbiddenError):
        msg = "Access denied"
        if len(exc.args) > 0:
            msg = exc.args[0]
        return CustomORJSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=error_detail(msg),
        )

    @app.exception_handler(ServerClientError)
    async def server_client_error_handler(request: Request, exc: ServerClientError):
        return CustomORJSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": get_server_client_error_details(exc)},
        )

    @app.exception_handler(OSError)
    async def os_error_handler(request, exc: OSError):
        if exc.errno in [36, 63]:
            return CustomORJSONResponse(
                {"detail": "Filename too long"},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        raise exc

    @app.middleware("http")
    async def log_request(request: Request, call_next):
        start_time = time.time()
        response: Response = await call_next(request)
        process_time = time.time() - start_time
        # log process_time to be used in the log_http_metrics middleware
        request.state.process_time = process_time
        logger.debug(
            "Processed request %s %s in %s. Status: %s",
            request.method,
            request.url,
            f"{process_time:0.6f}s",
            response.status_code,
        )
        return response

    if settings.SERVER_PROFILING_ENABLED:
        from pyinstrument import Profiler

        @app.middleware("http")
        async def profile_request(request: Request, call_next):
            profiling = request.query_params.get("profile", False)
            if profiling:
                profiler = Profiler()
                profiler.start()
                respone = await call_next(request)
                profiler.stop()
                with open("profiling_results.html", "w+") as f:
                    f.write(profiler.output_html())
                return respone
            else:
                return await call_next(request)

    # this middleware must be defined after the log_request middleware
    @app.middleware("http")
    async def log_http_metrics(request: Request, call_next):
        def _extract_project_name(request: Request):
            project_name = None
            prefix = "/api/project/"
            if request.url.path.startswith(prefix):
                rest = request.url.path[len(prefix) :]
                project_name = rest.split("/", 1)[0] if rest else None

            return project_name

        project_name = _extract_project_name(request)
        response: Response = await call_next(request)

        REQUEST_DURATION.labels(
            method=request.method,
            endpoint=request.url.path,
            http_status=response.status_code,
            project_name=project_name,
        ).observe(request.state.process_time)

        REQUESTS_TOTAL.labels(
            method=request.method,
            endpoint=request.url.path,
            http_status=response.status_code,
            project_name=project_name,
        ).inc()
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
        return CustomORJSONResponse(content={"status": "running"})

    if ui and Path(__file__).parent.joinpath("statics").exists():
        app.mount(
            "/", StaticFiles(packages=["dstack._internal.server"], html=True), name="statics"
        )

        @app.exception_handler(404)
        async def custom_http_exception_handler(request, exc):
            if (
                request.url.path.startswith("/api")
                or _is_proxy_request(request)
                or _is_prometheus_request(request)
            ):
                return CustomORJSONResponse(
                    {"detail": exc.detail},
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            else:
                return HTMLResponse(
                    importlib.resources.files("dstack._internal.server")
                    .joinpath("statics/index.html")
                    .read_text()
                )

    else:

        @app.get("/")
        async def index():
            return RedirectResponse("/api/docs")


def _is_proxy_request(request: Request) -> bool:
    if request.url.path.startswith("/proxy"):
        return True
    # Attempt detecting requests originating from services proxied by dstack-proxy.
    # Such requests can "leak" to dstack server paths if the service does not support
    # running under a path prefix properly.
    referrer = URL(request.headers.get("Referer", ""))
    return (
        referrer.netloc == "" or referrer.netloc == request.url.netloc
    ) and referrer.path.startswith("/proxy")


def _is_prometheus_request(request: Request) -> bool:
    return request.url.path.startswith("/metrics")


def _sentry_traces_sampler(sampling_context: SamplingContext) -> float:
    parent_sampling_decision = sampling_context["parent_sampled"]
    if parent_sampling_decision is not None:
        return float(parent_sampling_decision)
    transaction_context = sampling_context["transaction_context"]
    name = transaction_context.get("name")
    if name is not None:
        if name.startswith("background."):
            return settings.SENTRY_TRACES_BACKGROUND_SAMPLE_RATE
    return settings.SENTRY_TRACES_SAMPLE_RATE


def _print_dstack_logo():
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


def _get_server_config_dir() -> str:
    return str(SERVER_CONFIG_FILE_PATH).replace(os.path.expanduser("~"), "~", 1)
