"""
Generates OpenAPI schema from dstack server app.
"""

import json

import mkdocs_gen_files

from dstack._internal.server.main import app
from dstack._internal.settings import DSTACK_VERSION

app.title = "OpenAPI Spec"
app.servers = [
    {"url": "http://localhost:3000", "description": "Local server"},
    {"url": "https://sky.dstack.ai", "description": "Managed server"},
]
app.version = DSTACK_VERSION or "0.0.0"
with mkdocs_gen_files.open("docs/reference/api/rest/openapi.json", "w") as f:
    json.dump(app.openapi(), f)
