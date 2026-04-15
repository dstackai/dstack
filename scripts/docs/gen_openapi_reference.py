"""
Generates OpenAPI schema from dstack server app.
"""

import json
import logging
import os
from pathlib import Path

from dstack._internal.server.main import app
from dstack._internal.settings import DSTACK_VERSION

disable_env = "DSTACK_DOCS_DISABLE_OPENAPI_REFERENCE"
if os.environ.get(disable_env):
    logging.getLogger("mkdocs.plugins.dstack.openapi").warning(
        "OpenAPI reference generation is disabled"
    )
    exit(0)

app.title = "OpenAPI Spec"
app.servers = [
    {"url": "http://localhost:3000", "description": "Local server"},
    {"url": "https://sky.dstack.ai", "description": "Managed server"},
]
app.version = DSTACK_VERSION or "0.0.0"
output_path = Path("docs/docs/reference/api/http/openapi.json")
output_path.parent.mkdir(parents=True, exist_ok=True)
new_content = json.dumps(app.openapi())
if not output_path.exists() or output_path.read_text() != new_content:
    output_path.write_text(new_content)
