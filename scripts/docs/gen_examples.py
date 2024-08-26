"""
Copies examples/**/README.md files as docs/examples/**/index.md
"""

import logging
import os

import mkdocs_gen_files

FILE_PATTERN = "examples/**/README.md"
logger = logging.getLogger("mkdocs.plugins.dstack.examples")

disable_env = "DSTACK_DOCS_DISABLE_EXAMPLES"
if os.environ.get(disable_env):
    logger.warning(f"Examples generation is disabled: {disable_env} is set")
    exit()

logger.info("Generating examples documentation...")


for root, dirs, files in os.walk("examples"):
    for file in files:
        if file == "README.md":
            src_file = os.path.join(root, file)
            with open(src_file, "r") as f:
                text = f.read()
            src_dir = os.path.dirname(src_file)
            # dest_dir = os.path.join("docs", src_dir)
            dest_file = os.path.join(src_dir, "index.md")
            dest = mkdocs_gen_files._get_file(dest_file, new=True)
            with mkdocs_gen_files.open(dest, "w") as f:
                f.write(text)
