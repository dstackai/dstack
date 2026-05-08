# Documentation setup

## 1. Clone the repo:

```shell
git clone https://github.com/dstackai/dstack
cd dstack
```

## 2. Install uv:

https://docs.astral.sh/uv/getting-started/installation

```shell
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 3. Install `dstack` with all extras and dev dependencies:

> [!WARNING]
> Building documentation requires `python_version >= 3.11`.

```shell
uv sync --all-extras
```

`dstack` will be installed into the project's `.venv` in editable mode.

## 4. (Recommended) Install pre-commit hooks:

Code formatting and linting can be done automatically on each commit with `pre-commit` hooks:

```shell
uv run pre-commit install
```

## 5. Preview documentation

To preview the documentation, run the follow command:

```shell
uv run mkdocs serve --livereload -s
```

The `--livereload` flag is required to work around live-reload bugs in recent `mkdocs` versions.

If you want to build static files, you can use the following command:

```shell
uv run mkdocs build -s
```

## Documentation build system

The documentation uses a custom build system with MkDocs hooks to generate various files dynamically.

### Disable flags

Use these in `.envrc` to disable expensive docs regeneration, especially during `mkdocs serve` auto-reload. Set any of them to disable the corresponding artifact.

```shell
export DSTACK_DOCS_DISABLE_LLM_TXT=1
export DSTACK_DOCS_DISABLE_CLI_REFERENCE=1
export DSTACK_DOCS_DISABLE_YAML_SCHEMAS=1
export DSTACK_DOCS_DISABLE_OPENAPI_REFERENCE=1
export DSTACK_DOCS_DISABLE_REST_PLUGIN_SPEC_REFERENCE=1
```

### Build hooks

The build process is customized via hooks in `scripts/docs/hooks.py`:

#### 1. Schema reference expansion

Files in `docs/reference/**/*.md` can use `#SCHEMA#` placeholders that are expanded with generated schema documentation during the build.

#### 2. llms.txt generation

Two files are generated for LLM consumption:

- **llms.txt**: Structured overview of documentation with titles and descriptions
  - Generated from mkdocs nav structure
  - Includes sections: Getting started, Concepts, Guides, Examples
  - Excludes: Reference section
  - Configuration: `scripts/docs/gen_llms_files.py` (INCLUDE_SECTIONS, EXCLUDE_SECTIONS)

- **llms-full.txt**: Full concatenation of all pages from llms.txt
  - Contains complete markdown content of all included pages

The generation logic is in `scripts/docs/gen_llms_files.py` and uses:
- `site_name`, `site_description`, `site_url` from `mkdocs.yml`
- Page titles from mkdocs nav structure
- Page descriptions from markdown frontmatter

**Adding descriptions**: To add descriptions to pages, add YAML frontmatter:

```yaml
---
title: Page Title
description: Short description of what this page covers
---
```

For examples, add frontmatter to the page files (e.g., `mkdocs/docs/examples/training/trl.md`).

#### 3. Skills discovery

The build creates `.well-known/skills/` directory structure for skills discovery:
- Reads `skills/dstack/SKILL.md`
- Parses name and description from frontmatter
- Generates `.well-known/skills/index.json`
- Copies SKILL.md to both `.well-known/skills/dstack/` and site root

#### 4. HTTP API reference

The HTTP API reference is generated from the FastAPI OpenAPI schema:

- `scripts/docs/gen_openapi_reference.py` writes `mkdocs/docs/reference/http/openapi.json`,
  keeps the per-tag Markdown pages in sync, and updates the generated tag list in the HTTP API
  index page.
- Tag pages use `!!swagger openapi.json tag="<tag>"!!`. Keep tag names exactly as they appear
  in the OpenAPI schema.
- `scripts/docs/hooks.py` expands the `!!swagger` directive into the Swagger UI container and
  the hidden operation headings that MkDocs uses for the page table of contents.
- `mkdocs/assets/javascripts/swagger.js` loads the shared `openapi.json`, filters it by tag on
  the client, and adapts Swagger UI markup to the docs layout.
- `mkdocs/assets/stylesheets/swagger.css` contains Swagger-specific styling and should stay
  scoped under `.dstack-swagger-ui`.

Keep hook logic limited to build-time Markdown/page structure, generated assets, and data
attributes needed by the client. Small presentation changes belong in `swagger.css`; small
behavior changes belong in `swagger.js`.

If the HTTP API reference needs deeper structural customization, such as replacing major Swagger
UI panels, request/response rendering, model rendering, or "try it out" behavior, prefer moving
toward a dedicated local bundle or custom Swagger UI layout instead of adding more DOM patching.
That bundle can still use the single generated `openapi.json` and filter by tag on the client, so
we should not reintroduce per-tag OpenAPI files unless there is a concrete reason.

### File structure

```
mkdocs/                         # docs_dir for the mkdocs site
├── index.md                    # Homepage
├── docs/                       # /docs/ URL section
│   ├── index.md                # Getting started
│   ├── installation.md
│   ├── quickstart.md
│   ├── concepts/               # Concept pages
│   ├── guides/                 # How-to guides
│   ├── reference/              # API reference (schema expansion)
│   └── examples/               # Example pages (inline source code)
│       └── training/
│           └── trl.md          # Page content with frontmatter
├── blog/                       # Blog posts
├── overrides/                  # Theme customization
├── layouts/                    # Social card layouts
└── assets/                     # Stylesheets, images, fonts

scripts/docs/
├── hooks.py                    # MkDocs build hooks
├── gen_llms_files.py           # llms.txt generation
├── gen_schema_reference.py     # Schema expansion
└── gen_cli_reference.py        # CLI reference generation

skills/
└── dstack/
    └── SKILL.md                # Skills discovery content
```

### Testing changes

When modifying the build system:

1. Test local build: `uv run mkdocs build -s`
2. Check generated files in `site/`:
   - `site/llms.txt`
   - `site/llms-full.txt`
   - `site/.well-known/skills/index.json`
3. Verify example pages render correctly
4. Check that descriptions appear in llms.txt
