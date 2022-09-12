import os
import webbrowser

import pkg_resources
from fastapi import FastAPI
from starlette.responses import HTMLResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from dstack.dashboard import repos, runs, artifacts, secrets, tags, logs
from dstack.repo import load_repo_data

app = FastAPI(docs_url="/api/docs")
app.include_router(repos.router)
app.include_router(runs.router)
app.include_router(artifacts.router)
app.include_router(secrets.router)
app.include_router(tags.router)
app.include_router(logs.router)


@app.on_event("startup")
async def startup_event():
    url = f"http://{os.getenv('DSTACK_DASHBOARD_HOST')}:{os.getenv('DSTACK_DASHBOARD_PORT')}"
    try:
        repo_data = load_repo_data()
        url += f"/{repo_data.repo_user_name}/{repo_data.repo_name}"
    except Exception:
        pass
    print(f"The dashboard is available at {url}")
    if os.getenv('DSTACK_DASHBOARD_HEADLESS').strip().lower() != "true":
        webbrowser.open(url)


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
