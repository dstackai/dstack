# Repository Guidelines

## Project Structure & Module Organization
- Core Python package lives in `src/dstack`; internal modules (including server) sit under `_internal`, API surfaces under `api`, and plugin integrations under `plugins`.
- Tests reside in `src/tests` and mirror package paths; add new suites alongside the code they cover.
- Frontend lives in `frontend` (React/webpack) and is built into `src/dstack/_internal/server/statics`.
- Docs sources are in `docs` with extra contributor notes in `contributing/*.md`; examples for users sit in `examples/`.

## Build, Test, and Development Commands
- Install deps (editable package with extras): `uv sync --all-extras` (uses `.venv` in repo).
- Run CLI/server from source: `uv run dstack ...` (e.g., `uv run dstack server --port 8000`).
- Lint/format: `uv run ruff check .` and `uv run ruff format .`.
- Type check: `uv run pyright -p .`.
- Test suite: `uv run pytest`.
- Frontend: from `frontend/` run `npm install`, `npm run build`, then copy `frontend/build` into `src/dstack/_internal/server/statics/`; for dev, `npm run start` with API on port 8000.

## Coding Style & Naming Conventions
- Python targets 3.9+ with 4-space indentation and max line length of 99 (see `ruff.toml`; `E501` is ignored but keep lines readable).
- Imports are sorted via Ruff’s isort settings (`dstack` treated as first-party).
- Prefer pydantic-style models in `core/models`.
- Tests use `test_*.py` modules and `test_*` functions; fixtures live near usage.

## Testing Guidelines
- Default to `uv run pytest`. Use markers from `tests/conftest.py` like `--runpostgres` if need to include specific tests.
- Group tests for the same unit (function/class) using `Test*` classes that mirror unit's name.
- Keep tests hermetic (network disabled except localhost per `pytest.ini`); stub cloud calls with mocks.

## Commit & Pull Request Guidelines
- Commit messages follow the existing style: short, imperative summaries (e.g., “Fix exclude_not_available ignored”); include rationale in the body if needed.
- For PRs, describe behavior changes and link related issues.
- Include screenshots or terminal output when touching UX/CLI messages or frontend flows.
- Always disclose AI Assistance in PRs.
