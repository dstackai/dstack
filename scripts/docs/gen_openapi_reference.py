"""
Generates OpenAPI schema from dstack server app.
"""
import json

import mkdocs_gen_files

import dstack.version
from dstack._internal.server.main import app

app.title = "REST API"
app.description = (
    "The REST API enables running tasks, services, and managing runs programmatically."
)
app.servers = [
    {"url": "http://localhost:3000", "description": "Local server"},
    {"url": "https://cloud.dstack.ai", "description": "Managed server"},
]
app.version = dstack.version.__version__ or "0.0.0"
with mkdocs_gen_files.open("docs/reference/api/rest/openapi.json", "w") as f:
    json.dump(app.openapi(), f)
