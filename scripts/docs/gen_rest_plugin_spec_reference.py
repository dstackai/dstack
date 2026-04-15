"""
Generates OpenAPI schema from an example REST plugin.
"""

import json
import logging
import os
from pathlib import Path

from dstack._internal.settings import DSTACK_VERSION

logger = logging.getLogger("mkdocs.plugins.dstack.rest_plugin_schema")
disable_env = "DSTACK_DOCS_DISABLE_REST_PLUGIN_SPEC_REFERENCE"
if os.environ.get(disable_env):
    logger.warning("REST plugin spec reference generation is disabled")
    exit(0)

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
output_path = Path("docs/docs/reference/plugins/rest/rest_plugin_openapi.json")
output_path.parent.mkdir(parents=True, exist_ok=True)
new_content = json.dumps(app.openapi())
if not output_path.exists() or output_path.read_text() != new_content:
    output_path.write_text(new_content)
