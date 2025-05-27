"""
Generates OpenAPI schema from an example REST plugin.
"""

import json

import mkdocs_gen_files

from dstack._internal.settings import DSTACK_VERSION
from examples.plugins.example_plugin_server.app.main import app

app.title = "REST Plugin OpenAPI Spec"
app.servers = [
    {"url": "http://localhost:8000", "description": "Local server"},
]
app.version = DSTACK_VERSION or "0.0.0"
with mkdocs_gen_files.open(
    "docs/reference/plugins/rest_plugin/rest_plugin_openapi.json", "w"
) as f:
    json.dump(app.openapi(), f)
