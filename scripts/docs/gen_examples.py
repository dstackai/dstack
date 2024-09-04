"""
Copies examples/**/README.md files as docs/examples/**/index.md
"""

import logging
import os
from fnmatch import fnmatch
from pathlib import Path

import mkdocs_gen_files
from mkdocs.structure.files import File

FILE_PATTERN = "examples/**/index.md"
logger = logging.getLogger("mkdocs.plugins.dstack.examples")

disable_env = "DSTACK_DOCS_DISABLE_EXAMPLES"
if os.environ.get(disable_env):
    logger.warning(f"Examples generation is disabled: {disable_env} is set")
    exit()

logger.info("Generating examples documentation...")

file: File
for file in mkdocs_gen_files.files:
    if not fnmatch(file.src_uri, FILE_PATTERN):
        continue
    p = (Path(file.src_dir).parent / file.src_uri).parent / "README.md"
    with open(p, "r") as f:
        text = f.read()
    with mkdocs_gen_files.open(file.src_uri, "w") as f:
        f.write(text)
