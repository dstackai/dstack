"""
Generates OpenAPI schema from an example REST plugin.
"""

import json
import logging

import mkdocs_gen_files

from dstack._internal.settings import DSTACK_VERSION

logger = logging.getLogger("mkdocs.plugins.dstack.rest_plugin_schema")

try:
    from example_plugin_server.main import app
except ImportError:
    logger.warning(
        "No module named 'example_plugin_server'."
        " The REST Plugin API won't be generated."
        " Run 'uv pip install examples/plugins/example_plugin_server' to install 'example_plugin_server'."
    )
    exit(0)

app.title = "REST Plugin OpenAPI Spec"
app.servers = [
    {"url": "http://localhost:8000", "description": "Local server"},
]
app.version = DSTACK_VERSION or "0.0.0"
with mkdocs_gen_files.open(
    "docs/reference/plugins/rest_plugin/rest_plugin_openapi.json", "w"
) as f:
    json.dump(app.openapi(), f)
