import os
import uuid

import pkg_resources
from fastapi import FastAPI
from starlette.responses import HTMLResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from dstack.hub.db.migrate import migrate
from dstack.hub.db.models import User
from dstack.hub.repository.user import UserManager
from dstack.hub.routers import (
    artifacts,
    hub,
    jobs,
    link,
    logs,
    repos,
    runners,
    runs,
    secrets,
    tags,
    users,
)

app = FastAPI(docs_url="/api/docs")
app.include_router(users.router)
app.include_router(hub.router)
app.include_router(runs.router)
app.include_router(jobs.router)
app.include_router(runners.router)
app.include_router(secrets.router)
app.include_router(logs.router)
app.include_router(artifacts.router)
app.include_router(tags.router)
app.include_router(repos.router)
app.include_router(link.router)


@app.on_event("startup")
async def startup_event():
    await migrate()
    admin_user = await update_admin_user()

    url = f"http://{os.getenv('DSTACK_HUB_HOST')}:{os.getenv('DSTACK_HUB_PORT')}?token={admin_user.token}"
    print(f"The hub is available at {url}")


async def update_admin_user() -> User:
    admin_user = await UserManager.get_user_by_name("admin")
    if admin_user is None:
        admin_user = await UserManager.create_admin()
    elif os.getenv("DSTACK_HUB_ADMIN_TOKEN") is not None and admin_user.token != os.getenv(
        "DSTACK_HUB_ADMIN_TOKEN"
    ):
        admin_user.token = os.getenv("DSTACK_HUB_ADMIN_TOKEN")
        await UserManager.save(admin_user)
    return admin_user


app.mount("/", StaticFiles(packages=["dstack.hub"], html=True), name="static")


# noinspection PyUnusedLocal
@app.exception_handler(404)
async def custom_http_exception_handler(request, exc):
    if request.url.path.startswith("/api"):
        return JSONResponse({"message": exc.detail}, status_code=404)
    else:
        return HTMLResponse(pkg_resources.resource_string(__name__, "statics/index.html"))
