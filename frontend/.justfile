# Justfile for building frontend
#
# Run `just` to see all available commands

default:
    @just --list

[private]
install-frontend:
    #!/usr/bin/env bash
    set -e
    cd {{source_directory()}}
    npm install

build-frontend:
    #!/usr/bin/env bash
    set -e
    cd {{source_directory()}}
    npm run build
    cp -r build/ ../src/dstack/_internal/server/statics/
