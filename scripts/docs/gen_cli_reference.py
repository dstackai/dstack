"""
Populates CLI reference pages with actual command output.
Finds the pattern in docs/references/cli/*.md and replace it with the output of the command.
"""

import concurrent
import concurrent.futures
import logging
import os
import re
import shlex
import subprocess
from fnmatch import fnmatch
from functools import cache

import mkdocs_gen_files
from mkdocs.structure.files import File

FILE_PATTERN = "docs/reference/cli/dstack/*.md"
logger = logging.getLogger("mkdocs.plugins.dstack.cli")

DISABLE_ENV = "DSTACK_DOCS_DISABLE_CLI_REFERENCE"


@cache  # TODO make caching work
def call_dstack(command: str) -> str:
    return subprocess.check_output(shlex.split(command)).decode()


def sub_help(match: re.Match) -> str:
    logger.info("Generating help for `%s`", match.group(1))
    try:
        output = call_dstack(match.group(1))
    except subprocess.CalledProcessError:
        logger.error("Failed to run `%s`", match.group(1))
        return match.group(0)
    return f"```shell\n$ {match.group(1)}\n{output}\n```"


def process_file(file: File):
    logger.debug(file.src_uri)
    if not fnmatch(file.src_uri, FILE_PATTERN):
        return
    logger.debug("Looking for CLI `dstack <options> --help` calls in %s", file.src_uri)
    with mkdocs_gen_files.open(file.src_uri, "r") as f:
        text = f.read()
    # Pattern:
    # ```shell
    # $ dstack <options> --help
    # #GENERATE#
    # ```
    text = re.sub(r"```shell\s*\n\$ (dstack .*--help)\s*\n#GENERATE#\s*\n```", sub_help, text)
    with mkdocs_gen_files.open(file.src_uri, "w") as f:
        f.write(text)


def main():
    if os.environ.get(DISABLE_ENV):
        logger.warning(f"CLI reference generation is disabled: {DISABLE_ENV} is set")
        exit()
    # Sequential processing take > 10s
    with concurrent.futures.ThreadPoolExecutor() as pool:
        futures = []
        for file in mkdocs_gen_files.files:
            futures.append(pool.submit(process_file, file))
        concurrent.futures.wait(futures)


main()
