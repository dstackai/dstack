import os
import time
from contextlib import asynccontextmanager

import pkg_resources
from fastapi import FastAPI, Request
from rich.prompt import Confirm
from starlette.responses import HTMLResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from dstack import version
from dstack._internal.cli.utils.config import CLIConfigManager
from dstack._internal.hub.background import start_background_tasks
from dstack._internal.hub.db.migrate import migrate
from dstack._internal.hub.db.models import User
from dstack._internal.hub.repository.projects import ProjectManager
from dstack._internal.hub.repository.users import UserManager
from dstack._internal.hub.routers import (
    artifacts,
    backends,
    configurations,
    gateways,
    jobs,
    link,
    logs,
    projects,
    repos,
    runners,
    runs,
    secrets,
    storage,
    tags,
    users,
)
from dstack._internal.hub.utils.logging import configure_logger
from dstack._internal.hub.utils.ssh import generate_hub_ssh_key_pair
from dstack._internal.utils import logging

configure_logger()
logger = logging.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await migrate()
    admin_user = await update_admin_user()
    await create_default_project(admin_user)
    scheduler = start_background_tasks()
    base_url = f"http://{os.getenv('DSTACK_SERVER_HOST')}:{os.getenv('DSTACK_SERVER_PORT')}"
    url = f"{base_url}?token={admin_user.token}"
    create_default_project_config(base_url, admin_user.token)
    generate_hub_ssh_key_pair()
    print(
        f"\nThe dstack server {version.__version__ if version.__version__ else '(no version)'} is running at:\n{url}"
    )
    backends_exist = await default_project_backends_exist()
    if not backends_exist:
        default_project_settings_url = (
            f"{base_url}/projects/{DEFAULT_PROJECT_NAME}/settings?token={admin_user.token}"
        )
        print(f"\nConfigure one or more cloud backends at:\n{default_project_settings_url}")
    yield
    scheduler.shutdown()


app = FastAPI(docs_url="/api/docs", lifespan=lifespan)
app.include_router(users.router)
app.include_router(projects.router)
app.include_router(backends.root_router)
app.include_router(backends.project_router)
app.include_router(runs.root_router)
app.include_router(runs.project_router)
app.include_router(jobs.router)
app.include_router(runners.router)
app.include_router(secrets.router)
app.include_router(logs.router)
app.include_router(artifacts.router)
app.include_router(storage.router)
app.include_router(tags.router)
app.include_router(repos.router)
app.include_router(link.router)
app.include_router(configurations.router)
app.include_router(gateways.router)

DEFAULT_PROJECT_NAME = "main"


@app.middleware("http")
async def app_logging(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    path = request.url.path
    request_dict = {"method": request.method, "path": path}
    if path.startswith("/api/"):
        logger.debug(
            {
                "request": request_dict,
                "process_time": process_time,
            }
        )
    return response


async def update_admin_user() -> User:
    admin_user = await UserManager.get_user_by_name("admin")
    if admin_user is None:
        admin_user = await UserManager.create_admin()
    elif os.getenv("DSTACK_SERVER_ADMIN_TOKEN") is not None and admin_user.token != os.getenv(
        "DSTACK_SERVER_ADMIN_TOKEN"
    ):
        admin_user.token = os.getenv("DSTACK_SERVER_ADMIN_TOKEN")
        await UserManager.save(admin_user)
    return admin_user


async def create_default_project(user: User) -> bool:
    default_project = await ProjectManager.get(DEFAULT_PROJECT_NAME)
    if default_project is not None:
        return False
    default_project = await ProjectManager.create(
        user=user, project_name=DEFAULT_PROJECT_NAME, members=[]
    )
    return True


async def default_project_backends_exist() -> bool:
    default_project = await ProjectManager.get(DEFAULT_PROJECT_NAME)
    if default_project is not None:
        backend_infos = await ProjectManager.list_backend_infos(default_project)
        if len(backend_infos) > 0:
            return True
    return False


def create_default_project_config(url: str, token: str):
    cli_config_manager = CLIConfigManager()
    default_project_config = cli_config_manager.get_default_project_config()
    project_config = cli_config_manager.get_project_config(DEFAULT_PROJECT_NAME)
    # "default", "local" are old default project names
    default = default_project_config is None or default_project_config.name in ["default", "local"]
    if project_config is None or default_project_config is None:
        cli_config_manager.configure_project(
            name=DEFAULT_PROJECT_NAME, url=url, token=token, default=default
        )
        cli_config_manager.save()
        return
    if project_config.url != url or project_config.token != token:
        if Confirm.ask(
            f"The default project in {cli_config_manager.dstack_dir / 'config.yaml'} is outdated. "
            f"Update it?"
        ):
            cli_config_manager.configure_project(
                name=DEFAULT_PROJECT_NAME, url=url, token=token, default=True
            )
        cli_config_manager.save()
        return


app.mount("/", StaticFiles(packages=["dstack._internal.hub"], html=True), name="static")


# noinspection PyUnusedLocal
@app.exception_handler(404)
async def custom_http_exception_handler(request, exc):
    if request.url.path.startswith("/api"):
        return JSONResponse({"detail": exc.detail}, status_code=404)
    else:
        return HTMLResponse(pkg_resources.resource_string(__name__, "statics/index.html"))
