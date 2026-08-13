# Root justfile
#
# This justfile serves as the main entry point to recipes from different components.
#
# Run `just` to see all available commands.
#
# Components:
# * runner/.justfile – Building and uploading dstack runner and shim
# * frontend/.justfile – Building and running the frontend
# * mkdocs/.justfile – Building and previewing the docs site
# * website/.justfile – Building and previewing the React landing page
# * .tox.justfile – Running Python tests via tox

set minimum-version := '1.55.0'

[doc("Building and uploading dstack runner and shim")]
mod runner "runner/.justfile"

[doc("Running Python tests via tox")]
mod tox ".tox.justfile"

set allow-duplicate-recipes

import "frontend/.justfile"

import "mkdocs/.justfile"

import "website/.justfile"

[default]
[private]
default:
    @just --list --list-submodules --unsorted
