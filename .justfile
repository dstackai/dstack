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

default:
    @just --list

set allow-duplicate-recipes

import "runner/.justfile"

import "frontend/.justfile"

import "mkdocs/.justfile"
