# Justfile for the React landing page (website/)
#
# Run `just` from the repo root to see all available commands.
# Recipes run from the repo root, so paths below are repo-relative.

# Install the landing's dependencies
website-install:
    cd website && npm ci

# Live-edit the landing (Vite dev server on http://127.0.0.1:5173).
# By default docs/blog links are same-origin (/docs, /blog) — which 404 in standalone dev.
# Pass a base to point them at a live site while iterating, e.g.:
#   just website-dev https://dstack.ai
website-dev base="":
    cd website && VITE_DOCS_BASE="{{base}}" npm run dev

# Build only the landing to website/dist
website-build:
    cd website && npm run build

# Build the combined site (landing + docs + blog) into ./site
site-build:
    ./scripts/docs/build_site.sh

# Serve the combined ./site locally for integrated preview (http://127.0.0.1:8001)
site-serve:
    uv run python -m http.server 8001 --directory site
