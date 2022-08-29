import os

import pkg_resources
from fastapi import FastAPI
from starlette.responses import HTMLResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from dstack.dashboard import repos, runs, artifacts, secrets, tags

app = FastAPI(docs_url="/api/docs")
app.include_router(repos.router)
app.include_router(runs.router)
app.include_router(artifacts.router)
app.include_router(secrets.router)
app.include_router(tags.router)


@app.on_event("startup")
async def startup_event():
    print(f"The dashboard API is available at http://{os.getenv('DSTACK_HOST')}:{os.getenv('DSTACK_PORT')}/api/docs")


app.mount("/", StaticFiles(packages=["dstack.dashboard"], html=True), name="static")


# noinspection PyUnusedLocal
@app.exception_handler(404)
async def custom_http_exception_handler(request, exc):
    if request.url.path.startswith("/api"):
        return JSONResponse({
            "message": exc.detail
        }, status_code=404)
    else:
        return HTMLResponse(pkg_resources.resource_string(__name__, 'statics/index.html'))
