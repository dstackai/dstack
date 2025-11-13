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
