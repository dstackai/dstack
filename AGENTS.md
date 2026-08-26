# Repository Guidelines

Before touching a subsystem, read the relevant notes in `contributing/`: `ARCHITECTURE.md`,
`PIPELINES.md`, `LOCKING.md`, `MIGRATIONS.md`, `RUNS-AND-JOBS.md`, `AUTOSCALING.md`,
`BACKENDS.md`, `GPUHUNT.md`, `PROXY.md`, `RUNNER-AND-SHIM.md`, `FRONTEND.md`, `DOCS.md`,
`DEVELOPMENT.md`, `RELEASE.md`.

## Project Structure & Module Organization
- Core Python package lives in `src/dstack`; internal modules (including server) sit under `_internal`, API surfaces under `api`, and plugin integrations under `plugins`.
- Tests reside in `src/tests` and mirror package paths; add new suites alongside the code they cover.
- Frontend lives in `frontend` (React/webpack) and is built into `src/dstack/_internal/server/statics`.
- Docs sources are in `mkdocs/docs/` with extra contributor notes in `contributing/*.md`.

## Build, Test, and Development Commands
- Install deps (editable package with extras): `uv sync --all-extras` (uses `.venv` in repo).
- Run CLI/server from source: `uv run dstack ...` (e.g., `uv run dstack server --port 8000`).
- Lint/format: `uv run ruff check .` and `uv run ruff format .`.
- Type check: `uv run pyright -p .`.
- Test suite: `uv run pytest`.
- Frontend: from `frontend/` run `npm install`, `npm run build`, then copy `frontend/build` into `src/dstack/_internal/server/statics/`; for dev, `npm run start` with API on port 8000.

## Coding Style & Naming Conventions
- Python targets 3.10+ with 4-space indentation and max line length of 99 (see `pyproject.toml`; `E501` is ignored but keep lines readable).
- Imports are sorted via Ruff’s isort settings (`dstack` treated as first-party).
- Keep primary/public functions before local helper functions in a module section.
- Roughly keep function definitions in the order they are referenced within a file so call flow stays easy to follow.
- Prefer early returns over nested `if`/`else` blocks when they make the control flow simpler.
- Keep private classes, exceptions, and similar implementation-specific types close to the private functions that use them unless they are shared more broadly in the module.
- Prefer pydantic-style models in `core/models`.
- Document attributes when the note adds behavior, compatibility, or semantic context that is not obvious from the name and type. Use attribute docstrings without leading newline.
- Tests use `test_*.py` modules and `test_*` functions; fixtures live near usage.
- Never make network calls inside a DB session or transaction. Fetch what you need before opening the session, or commit and close it before the call.
- Don't use function-level (inner) imports to break circular imports. Inject the dependency or move the shared code to a lower-level module instead.
- Never edit a migration that has already been applied or released; add a new migration instead.
- Derive paths under `SERVER_DIR_PATH` on access (a `get_*` function), not as module-level constants, so that patching `settings.SERVER_DIR_PATH` redirects all of them. Tests rely on this to keep server state out of the real `~/.dstack`.
- Preserve client/server backward compatibility when updating Pydantic models. New fields must be excluded from client requests when unset, for compatibility with older servers (see `core/compatibility/*.py`). If the allowed domain/type of an existing field is extended, server responses may need to be patched for older clients (see `server/compatibility/*.py`). No need to exclude new fields from server responses, since clients rely on `validate_extra_ignore`.

## Testing Guidelines
- Default to `uv run pytest`. Use markers from `src/tests/conftest.py` like `--runpostgres` if need to include specific tests.
- Scope the run to the change: for trivial or localized edits, run only the affected test modules, `Test*` classes, or `-k` selection instead of the whole suite. Reserve the full suite for broad or cross-cutting changes.
- Speed up large runs with `-n auto` (pytest-xdist), e.g. `uv run pytest -n auto`.
- Group tests for the same unit (function/class) using `Test*` classes that mirror unit's name.
- Keep tests hermetic (network disabled except localhost per `[tool.pytest.ini_options]` in `pyproject.toml`); stub cloud calls with mocks.
- Keep the suite fast. Never let a test wait on real time.
- Machinery that costs hundreds of milliseconds per test (spawning a subprocess, starting a container, generating a key, real HTTP) has to earn its place by covering something cheaper tests cannot. Say so in the test when it does. On the other hand, losing black-box coverage or making the test hard to follow is worse than the milliseconds it costs.

## Commit & Pull Request Guidelines
- Name branches `issue_{issue_num}_{title}` when the work tracks an issue (e.g. `issue_3959_replicated_alb_gateways`), and `pr_{title}` otherwise.
- Never create git tags. Tags are reserved for releases and are created only by the release process described in `contributing/RELEASE.md`. To mark or share a commit, push an appropriately named branch instead.
- Commit messages follow the existing style: short, imperative summaries (e.g., “Fix exclude_not_available ignored”); include rationale in the body if needed.
- For PRs, describe behavior changes and link related issues.
- Include screenshots or terminal output when touching UX/CLI messages or frontend flows.
