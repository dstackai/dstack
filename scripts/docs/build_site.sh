#!/usr/bin/env bash
#
# Build the combined dstack website: the React landing (website/) overlaid onto the
# MkDocs docs+blog build (site/). Produces a single publishable tree in ./site:
#
#   /                          -> React landing      (website/dist/index.html)
#   /website-assets, /static   -> React landing assets
#   /docs, /blog, /assets, ... -> MkDocs (untouched)
#   /404.html                  -> MkDocs (the landing build produces none)
#
# Used by both `just site-build` and the GitHub Action. Run from anywhere; the repo
# root is resolved from this script's location.
#
# Env:
#   SKIP_NPM_INSTALL=1   reuse website/node_modules instead of running `npm ci`
#                        (handy for fast local iteration; CI leaves it unset).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

echo "==> Building the React landing (website/)"
(
  cd website
  if [ "${SKIP_NPM_INSTALL:-}" != "1" ]; then
    npm ci
  fi
  npm run build
)

echo "==> Building the MkDocs docs + blog (site/)"
uv run mkdocs build -s

echo "==> Overlaying the landing onto site/"
# React owns only '/': its index.html replaces the MkDocs landing; website-assets/ and
# static/ are added alongside the MkDocs output. MkDocs's 404.html, /assets/, /docs/ and
# /blog/ are left untouched (the landing build intentionally produces no 404.html).
cp -R website/dist/. site/

echo "==> Done. Combined site is in $REPO_ROOT/site"
