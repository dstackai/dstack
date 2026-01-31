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
uv run mkdocs serve -w examples -s
```

If you want to build static files, you can use the following command:

```shell
uv run mkdocs build -s
```

## Documentation build system

The documentation uses a custom build system with MkDocs hooks to generate various files dynamically.

### Build hooks

The build process is customized via hooks in `scripts/docs/hooks.py`:

#### 1. Example materialization

Example pages like `examples/single-node-training/trl/index.md` are stubs that reference `README.md` files in the repository root:
- **Stub location**: `docs/examples/single-node-training/trl/index.md`
- **Content source**: `examples/single-node-training/trl/README.md`

During the build, the hook reads the README content and uses it for rendering the HTML page.

#### 2. Schema reference expansion

Files in `docs/reference/**/*.md` can use `#SCHEMA#` placeholders that are expanded with generated schema documentation during the build.

#### 3. llms.txt generation

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

For examples, add frontmatter to the `README.md` files in the repository root (e.g., `examples/single-node-training/trl/README.md`).

#### 4. Skills discovery

The build creates `.well-known/skills/` directory structure for skills discovery:
- Reads `skills/dstack/SKILL.md`
- Parses name and description from frontmatter
- Generates `.well-known/skills/index.json`
- Copies SKILL.md to both `.well-known/skills/dstack/` and site root

### File structure

```
docs/
├── docs/                    # Main documentation content
│   ├── index.md            # Getting started
│   ├── installation.md
│   ├── quickstart.md
│   ├── concepts/           # Concept pages
│   ├── guides/             # How-to guides
│   └── reference/          # API reference (schema expansion)
├── examples/               # Example stub files (index.md)
│   └── single-node-training/
│       └── trl/
│           └── index.md    # Stub referencing root README
└── overrides/              # Theme customization

examples/                    # Example content (repository root)
└── single-node-training/
    └── trl/
        ├── README.md       # Actual content with frontmatter
        └── train.dstack.yml

scripts/docs/
├── hooks.py                # MkDocs build hooks
├── gen_llms_files.py       # llms.txt generation
├── gen_schema_reference.py # Schema expansion
└── gen_cli_reference.py    # CLI reference generation

skills/
└── dstack/
    └── SKILL.md            # Skills discovery content
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
