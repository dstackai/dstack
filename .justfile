# Root justfile
#
# This justfile serves as the main entry point to recipes from different components.
#
# Run `just` to see all available commands.
#
# Components:
# * runner/justfile – Building and uploading dstack runner and shim

default:
    @just --list

set allow-duplicate-recipes

import "runner/.justfile"

import "frontend/.justfile"

docs-serve:
    uv run mkdocs serve --livereload -w examples -s
