# Development setup

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

```shell
uv sync --all-extras
```

`dstack` will be installed into the project's `.venv` in editable mode and can be run with `uv run dstack`.

Alternatively, if you want to manage virtual environments by yourself, you can install `dstack` into the activated virtual environment with `uv sync --all-extras --active`.

## 4. (Recommended) Install pre-commit hooks:

Code formatting and linting can be done automatically on each commit with `pre-commit` hooks:

```shell
uv run pre-commit install
```

## 5. (Recommended) Use pyright:

The CI runs `pyright` for type checking `dstack` Python code.
So we recommend you configure your IDE to use `pyright`/`pylance` with `standard` type checking mode.

You can also install `pyright` and run it from the CLI:

```shell
uv tool install pyright
pyright -p .
```

## 6. Frontend

See [FRONTEND.md](FRONTEND.md) for the details on how to build and develop the frontend.
