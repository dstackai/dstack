import os
import uuid

import pkg_resources
from fastapi import FastAPI
from sqlalchemy.orm import Session
from starlette.responses import HTMLResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from dstack.hub.db import metadata
from dstack.hub.db.users import User
from dstack.hub.routers import users

app = FastAPI(docs_url="/api/docs")
app.include_router(users.router)


@app.on_event("startup")
async def startup_event():
    metadata.create_all()
    admin_user = await update_admin_user()

    url = f"http://{os.getenv('DSTACK_HUB_HOST')}:{os.getenv('DSTACK_HUB_PORT')}?token={admin_user.token}"
    print(f"The hub is available at {url}")


async def update_admin_user() -> User:
    with Session(metadata.engine, expire_on_commit=False) as session:
        admin_user = session.get(User, "admin")
        if admin_user is None:
            admin_user = User(
                name="admin",
                token=os.getenv("DSTACK_HUB_ADMIN_TOKEN") or str(uuid.uuid4()),
            )
            session.add(admin_user)
            session.commit()
        elif os.getenv("DSTACK_HUB_ADMIN_TOKEN") is not None and admin_user.token != os.getenv(
            "DSTACK_HUB_ADMIN_TOKEN"
        ):
            admin_user.token = os.getenv("DSTACK_HUB_ADMIN_TOKEN")
            session.commit()

        session.expunge(admin_user)
    return admin_user


app.mount("/", StaticFiles(packages=["dstack.hub"], html=True), name="static")


# noinspection PyUnusedLocal
@app.exception_handler(404)
async def custom_http_exception_handler(request, exc):
    if request.url.path.startswith("/api"):
        return JSONResponse({"message": exc.detail}, status_code=404)
    else:
        return HTMLResponse(pkg_resources.resource_string(__name__, "statics/index.html"))
