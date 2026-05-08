# Justfile for building and previewing the docs site
#
# Run `just` to see all available commands

default:
    @just --list

# Preview the docs site with live-reload
mkdocs-serve:
    # --livereload works around live-reload bugs in recent mkdocs versions
    uv run mkdocs serve --livereload -s

# Build the docs site to ./site
mkdocs-build:
    uv run mkdocs build -s
