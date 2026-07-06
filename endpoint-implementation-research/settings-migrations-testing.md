# settings-migrations-testing

## Summary
Established ground truth for server settings, migrations, models, testing, linting, and packaging conventions in /Users/dstack/dstack. Settings are plain module-level constants in src/dstack/_internal/server/settings.py read via os.getenv/environ helpers with DSTACK_ or DSTACK_SERVER_ prefixes, documented in mkdocs/docs/reference/env.md; feature flags are DSTACK_FF_* on the FeatureFlags class in src/dstack/_internal/settings.py. Migrations are Alembic autogenerate (run from src/dstack/_internal/server with `alembic revision -m "..." --autogenerate`), rendered with render_as_batch=True for SQLite compat, stored under migrations/versions/<year>/. Models use DeclarativeBase BaseModel with UUIDType(binary=False) PKs, NaiveDateTime, EnumAsString, EncryptedString custom types, and pydantic-JSON-as-Text columns; multi-replica pipeline rows use PipelineModelMixin (lock_expires_at/lock_token/lock_owner). Test factories live in src/dstack/_internal/server/testing/common.py (not factories.py) with test_db/session fixtures in testing/conf.py; tests run via `uv run pytest src/tests` (add --runpostgres for Postgres). Lint is ruff 0.12.7, types are pyright standard mode; heavy deps are optional-dependencies extras (server, gateway, aws, ...) guarded by try/except ImportError.

## Key files
- src/dstack/_internal/server/settings.py — module-level constants; JobNetworkMode enum — All server env-var settings; docstring says 'Documented in reference/env.md'
- src/dstack/_internal/settings.py — FeatureFlags, DSTACK_VERSION, DSTACK_RELEASE — Global (non-server) settings; FeatureFlags class holds DSTACK_FF_* flags
- src/dstack/_internal/utils/env.py — Environ.get/get_bool/get_int/get_enum/get_callback; environ singleton — Typed env-var parsing helper used by newer settings
- src/dstack/_internal/server/models.py — BaseModel, PipelineModelMixin, NaiveDateTime, EncryptedString, DecryptedString, EnumAsString, constraint_naming_convention, RunModel, VolumeModel — All ORM models and custom column types
- src/dstack/_internal/server/alembic.ini —  — script_location=migrations; file_template puts revisions in <year>/MM_DD_HHMM_<rev>_<slug>.py
- src/dstack/_internal/server/migrations/env.py —  — render_as_batch=True (line 82), compare_type=True (line 81), target_metadata=BaseModel.metadata (line 16)
- src/dstack/_internal/server/migrations/versions/2026/03_04_2221_5e8c7a9202bc_add_exports.py —  — Recent example migration creating tables with UUIDType PKs, named FKs, batch_alter_table for indexes
- contributing/MIGRATIONS.md —  — Alembic command, expand-and-contract rules, one-table-per-migration, CREATE INDEX CONCURRENTLY guidance
- contributing/DEVELOPMENT.md —  — uv sync --all-extras; pre-commit; pyright standard mode
- CONTRIBUTING.md —  — uv run ruff check --fix; uv run ruff format; uv run pytest src/tests [--runpostgres]
- src/dstack/_internal/server/testing/common.py — create_user, create_project, create_repo, create_run, create_job, create_fleet, create_volume, create_gateway, create_instance, get_run_spec, ComputeMockSpec — THE factory module (testing/factories.py does not exist)
- src/dstack/_internal/server/testing/conf.py — test_db, session, postgres_container fixtures — test_db parametrized sqlite/postgres via indirect=True; postgres uses testcontainers
- src/tests/conftest.py — pytest_addoption(--runpostgres/--runui), disable_feature_flags — Re-exports testing.conf fixtures; autouse fixture forces all FeatureFlags to False
- src/tests/_internal/server/conftest.py — client, test_log_storage, image_config_mock, mock_gateway_connection — Server-level fixtures incl. httpx ASGI client against dstack._internal.server.main:app
- src/tests/_internal/server/background/pipeline_tasks/test_volumes.py —  — Canonical pipeline-task test: Fetcher/Worker fixtures, parametrized test_db, factories
- src/tests/_internal/server/background/scheduled_tasks/test_probes.py —  — Canonical scheduled-task test: calls process_probes() directly with mocked deps
- pyproject.toml —  — ruff/pyright/pytest config, dependency-groups dev, [project.optional-dependencies] extras incl. server/gateway/all
- src/dstack/_internal/server/services/storage/s3.py —  — Canonical optional-dependency import pattern (BOTO_AVAILABLE flag + try/except ImportError)
- mkdocs/docs/reference/env.md —  — User-facing docs for DSTACK_SERVER_* env vars (server section around lines 94-140)

## Details
# Conventions cheat-sheet (verified against code, 2026-07-03)

## 1. Server settings — `src/dstack/_internal/server/settings.py`

Plain module-level constants evaluated at import time. Module docstring (settings.py:1-3): *"Environment variables read by the dstack server. Documented in reference/env.md"* — the doc file is `mkdocs/docs/reference/env.md` (server env vars listed ~lines 94-140 with `{ #ANCHOR }` markers).

Naming: env var prefix is `DSTACK_SERVER_*` for server-behavior settings, bare `DSTACK_*` for cross-cutting ones (`DSTACK_DATABASE_URL`, `DSTACK_SENTRY_DSN`, `DSTACK_DB_POOL_SIZE`, `DSTACK_ACME_SERVER`). Python constant name drops the `DSTACK_` prefix (e.g. `SERVER_PORT`, `DATABASE_URL`).

Declaration patterns (all real examples):
- String w/ default: `SERVER_HOST = os.getenv("DSTACK_SERVER_HOST", "localhost")` (settings.py:28)
- Int: `SERVER_PORT = int(os.getenv("DSTACK_SERVER_PORT", "8000"))` (settings.py:29); `MAX_OFFERS_TRIED = int(os.getenv("DSTACK_SERVER_MAX_OFFERS_TRIED", 25))` (settings.py:54)
- Presence-based bool flag (set-to-anything = true): `SERVER_BACKGROUND_PROCESSING_DISABLED = os.getenv("DSTACK_SERVER_BACKGROUND_PROCESSING_DISABLED") is not None` followed by `SERVER_BACKGROUND_PROCESSING_ENABLED = not SERVER_BACKGROUND_PROCESSING_DISABLED` (settings.py:47-50). Same DISABLED/ENABLED pair pattern for `SERVER_CONFIG_DISABLED/ENABLED` (58-59), `DEFAULT_CREDS_DISABLED/ENABLED` (122-123), `SERVER_SSH_POOL_DISABLED/ENABLED` (152-153).
- Typed helper (`dstack._internal.utils.env.environ`, an `Environ` wrapper over `os.environ` — env.py:12-121, methods `get(name, *, default)`, `get_bool`, `get_int`, `get_enum(name, enum_cls, *, value_type, default)`, `get_callback(name, callback, *, default)`): e.g. `SERVER_METRICS_RUNNING_TTL_SECONDS = environ.get_int("DSTACK_SERVER_METRICS_RUNNING_TTL_SECONDS", default=3600)` (settings.py:83-85); enum example `JOB_NETWORK_MODE = environ.get_enum("DSTACK_SERVER_JOB_NETWORK_MODE", JobNetworkMode, value_type=int, default=DEFAULT_JOB_NETWORK_MODE)` (settings.py:178-183).
- Optional str normalized to None: `SERVER_DEFAULT_DOCKER_REGISTRY = os.getenv("DSTACK_SERVER_DEFAULT_DOCKER_REGISTRY") or None` (settings.py:132).
- Dev-only settings live at bottom under a `# Development settings` comment (settings.py:156-165), e.g. `SQL_ECHO_ENABLED`, `SERVER_PROFILING_ENABLED`.

Feature flags: NOT in server/settings.py. `class FeatureFlags` in `src/dstack/_internal/settings.py:40-52` — env vars of the form `DSTACK_FF_*`, class attrs must be bool, docstring says flags are temporary for large features in development. Current sole flag: `CLI_PRINT_JOB_CONNECTION_INFO = os.getenv("DSTACK_FF_CLI_PRINT_JOB_CONNECTION_INFO") is not None`. In tests, ALL feature flags are force-disabled by the autouse session fixture `disable_feature_flags` in `src/tests/conftest.py:51-62`; to test a flag, monkeypatch `FeatureFlags` per-test.

## 2. Alembic migrations — `src/dstack/_internal/server/migrations/`

Generate (contributing/MIGRATIONS.md:7-10):
```shell
cd src/dstack/_internal/server/
alembic revision -m "<some message>" --autogenerate
```
- `alembic.ini` lives at `src/dstack/_internal/server/alembic.ini`; `script_location = migrations`; `file_template = %%(year)d/%%(month).2d_%%(day).2d_%%(hour).2d%%(minute).2d_%%(rev)s_%%(slug)s` and `recursive_version_locations = true` — so files land in `migrations/versions/<YEAR>/MM_DD_HHMM_<rev12>_<slug>.py` (e.g. `versions/2026/06_19_0709_857d8fa7fcc5_add_gateway_replica_pipeline.py`).
- `migrations/env.py` uses `target_metadata = BaseModel.metadata` (env.py:16) and configures autogenerate with `compare_type=True, render_as_batch=True` (env.py:81-82). **`render_as_batch=True` is what makes ALTERs SQLite-compatible** — column adds/drops are emitted as `with op.batch_alter_table("<table>", schema=None) as batch_op:` blocks (see add_gateway_replica_pipeline migration lines 44-65). Plain `op.create_table`/`op.drop_table` used for new tables (add_exports migration lines 24-40).
- Column types in migrations: `sqlalchemy_utils.types.uuid.UUIDType(binary=False)` for UUIDs; `dstack._internal.server.models.NaiveDateTime()` for datetimes (migrations import `import dstack._internal.server.models` for this); `sa.String(length=100)`, `sa.Text()`, `sa.Boolean()`.
- Constraint naming comes from `constraint_naming_convention` (models.py:191-197): `pk_%(table_name)s`, `fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s`, `uq_%(table_name)s_%(column_0_name)s`, `ix_%(column_0_label)s` — migrations pass explicit names via `op.f(...)` (e.g. `name=op.f("fk_exports_project_id_projects")`).
- Multi-replica zero-downtime rules (contributing/MIGRATIONS.md): migrations must not break old replicas; use expand-and-contract for column removals/renames (remove = release 1: `deferred=True` stop reading; release 2: drop). Alter only ONE table per migration/transaction (Postgres ACCESS EXCLUSIVE deadlock risk, MIGRATIONS.md:47-49). Index creation should use `postgresql_concurrently=True` inside `with op.get_context().autocommit_block():`, pre-dropping with `if_exists=True` for retry safety (MIGRATIONS.md:51-75).
- Data backfills inside migrations use lightweight `sa.table(...)/sa.column(...)` partial definitions + `op.execute(sa.update(...))` — see 06_19_0709_857d8fa7fcc5 lines 22-89 (also shows the exact pattern used to retrofit pipeline columns: add nullable, backfill `last_processed_at=created_at` and status via `sa.case`, then `alter_column(..., nullable=False)`).
- `pyproject.toml` [tool.pyright] ignores `src/dstack/_internal/server/migrations/versions`.

## 3. models.py conventions — `src/dstack/_internal/server/models.py`

- Base: `class BaseModel(DeclarativeBase): metadata = MetaData(naming_convention=constraint_naming_convention)` (models.py:200-201). SQLAlchemy 2.0 style: `Mapped[...]` + `mapped_column(...)`.
- PK convention: `id: Mapped[uuid.UUID] = mapped_column(UUIDType(binary=False), primary_key=True, default=uuid.uuid4)` (`UUIDType` from `sqlalchemy_utils`). Table names are plural snake_case via `__tablename__` ("runs", "volumes", "gateway_computes").
- `PipelineModelMixin` (models.py:204-207) — REQUIRED for any row processed by the multi-replica-safe background pipeline machinery: `lock_expires_at: Mapped[Optional[datetime]] = mapped_column(NaiveDateTime)`, `lock_token: Mapped[Optional[uuid.UUID]] = mapped_column(UUIDType(binary=False))`, `lock_owner: Mapped[Optional[str]] = mapped_column(String(100))`. Models using it: RunModel, JobModel, GatewayModel, GatewayComputeModel, FleetModel, InstanceModel, VolumeModel, PlacementGroupModel, ComputeGroupModel, ServiceRouterWorkerSyncModel. Pipeline-processed models additionally carry `last_processed_at: Mapped[datetime] = mapped_column(NaiveDateTime, default=get_current_datetime)` (sometimes `skip_min_processing_interval: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())`) and a partial "fetch queue" index in `__table_args__`, e.g. VolumeModel (models.py:991-998):
  ```python
  Index("ix_volumes_pipeline_fetch_q", last_processed_at.asc(),
        postgresql_where=deleted == false(), sqlite_where=deleted == false())
  ```
  RunModel's variant filters on status: `postgresql_where=status.not_in(RunStatus.finished_statuses())` (models.py:466-471).
- Custom column types (all `TypeDecorator`s defined in models.py):
  - `NaiveDateTime` (models.py:57) — impl DateTime; strips tzinfo on write, re-attaches UTC on read. Used for every datetime column; python-side default is `dstack._internal.utils.common.get_current_datetime`.
  - `EncryptedString` (models.py:107) — impl String; binds `DecryptedString` pydantic-dual model (models.py:83, has `plaintext`, `decrypted`, `exc`, `get_plaintext_or_error()`); encrypt/decrypt funcs injected via `EncryptedString.set_encrypt_decrypt(...)` (wired by importing `dstack._internal.server.services.encryption` for side effect — see src/tests/_internal/server/conftest.py:9). Used e.g. `UserModel.token: Mapped[DecryptedString] = mapped_column(EncryptedString(200), unique=True)` (models.py:218), `BackendModel.auth = EncryptedString(20000)`.
  - `EnumAsString(enum_class, length, fallback_deserializer=None)` (models.py:152) — stores `enum.name` string; used for all status columns: `status: Mapped[VolumeStatus] = mapped_column(EnumAsString(VolumeStatus, 100), index=True)`.
- **No JSON column type.** Structured payloads are pydantic models serialized to `Text`: `run_spec: Mapped[str] = mapped_column(Text)` (models.py:445), `VolumeModel.configuration: Mapped[str] = mapped_column(Text)` (models.py:981), `JobModel.job_spec_data`, etc. Written as `run_spec.json()`, read as `RunSpec.parse_raw(run.run_spec)` (pydantic v1: `pydantic>=1.10.10,<2.0.0` + pydantic-duality).
- FKs: `mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))` + separate `relationship()`. Soft-delete convention: `deleted: Mapped[bool]` (+ optional `deleted_at`, `to_be_deleted` for pipeline-driven deletion). Bools added later use `server_default=false()` (from `sqlalchemy.sql`).
- Docstrings placed under fields as bare strings explain semantics (e.g. models.py:437 `"""`status` must be changed only via `switch_run_status()`."""`).

## 4. Testing

- Factories are in `src/dstack/_internal/server/testing/common.py` (**`testing/factories.py` does not exist**; the package has `common.py`, `conf.py`, `matchers.py`). All async, take `session: AsyncSession` first, `session.add(...)` + `await session.commit()`, return the model. Exact names (with a few exact signatures):
  - `async def create_user(session, name="test_user", created_at=..., global_role=GlobalRole.ADMIN, token=None, email=None, ssh_public_key=None, ssh_private_key=None, active=True, deleted=False) -> UserModel` (common.py:147)
  - `async def create_project(session, owner=None, name="test_project", created_at=..., ssh_private_key="", ssh_public_key="", is_public=False, templates_repo=None, deleted=False) -> ProjectModel` (common.py:200)
  - `async def create_repo(...)` (262), `async def create_backend(session, project_id, backend_type=BackendType.AWS, config=None, auth=None, ...)` (228)
  - `def get_run_spec(repo_id, run_name="test-run", configuration_path="dstack.yaml", profile=..., configuration=None, ssh_key_pub="user_ssh_key", ...) -> RunSpec` (341) — default configuration is `DevEnvironmentConfiguration(ide="vscode")`; pass e.g. `ServiceConfiguration(...)` to override.
  - `async def create_run(session, project, repo, user, fleet=None, gateway=None, run_name=None, status=RunStatus.SUBMITTED, ..., run_spec=None, ...) -> RunModel` (365) — serializes `run_spec.json()` into the Text column.
  - `async def create_job(session, run, ...) -> JobModel` (422); `async def create_fleet(...)` (758), `get_fleet_spec` (792), `get_fleet_configuration` (806); `async def create_gateway(...)` (639), `create_gateway_compute` (683); `async def create_instance(...)` (850), `get_instance_offer_with_availability` (964); `async def create_volume(session, project, user, status=..., created_at=..., last_processed_at=..., deleted_at=..., ...)` (1069), `get_volume_configuration` (1150), `get_volume_provisioning_data` (1188); `create_compute_group` (573), `create_placement_group` (1206), `create_probe` (619), `create_secret` (1301), `list_events` (1317), `get_auth_headers(token)` (141). Also `class ComputeMockSpec` (common.py:1404) inheriting all Compute* capability mixins, "Can be used to create Compute mocks that pass all isinstance() asserts".
- DB fixtures — `src/dstack/_internal/server/testing/conf.py`, re-exported in `src/tests/conftest.py` and `src/tests/_internal/server/conftest.py`:
  - `test_db` (pytest_asyncio fixture, function-scoped, conf.py:22-55): param "sqlite" (default; in-memory aiosqlite with StaticPool + check_same_thread=False, `BaseModel.metadata.create_all` — **migrations are NOT run in tests**) or "postgres" (testcontainers `PostgresContainer("postgres:16-alpine", driver="asyncpg")`, skipped unless `--runpostgres`; tables created once per session then `TRUNCATE ... RESTART IDENTITY CASCADE` between tests). Calls `override_db(db)` from `dstack._internal.server.db`.
  - `session` (conf.py:58-62): `async with test_db.get_session() as session: yield session`.
- Background-task test pattern (pipeline): `src/tests/_internal/server/background/pipeline_tasks/test_volumes.py` — class-level decorators:
  ```python
  @pytest.mark.asyncio
  @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
  class TestVolumeFetcher:
      async def test_...(self, test_db, session: AsyncSession, fetcher: VolumeFetcher): ...
  ```
  Fixtures construct pipeline components directly: `VolumeWorker(queue=Mock(), heartbeater=Mock(), pipeline_hinter=Mock())`, `VolumeFetcher(queue=asyncio.Queue(), queue_desired_minsize=1, min_processing_interval=timedelta(seconds=15), lock_timeout=timedelta(seconds=30), heartbeater=Mock())`; tests seed rows with factories, then `items = await fetcher.fetch(limit=10)` / call worker methods; lock behavior asserted via `lock_token/lock_expires_at/lock_owner`. Imports come from `dstack._internal.server.background.pipeline_tasks.volumes` (`VolumeFetcher, VolumePipeline, VolumePipelineItem, VolumeWorker`). Test dirs: `src/tests/_internal/server/background/pipeline_tasks/` (test_fleets.py, test_gateways.py, test_gateway_replicas.py, test_volumes.py, test_runs/, test_instances/, ...) and `.../scheduled_tasks/` (test_probes.py, test_events.py, ...). Scheduled-task tests call the task function directly (e.g. `from ...background.scheduled_tasks.probes import process_probes`; `pytestmark = pytest.mark.usefixtures("image_config_mock")`; freezegun `freeze_time` used).
  Note: pytest-asyncio runs in default (strict) mode — every async test/class needs explicit `@pytest.mark.asyncio`; no `asyncio_mode` is set in pyproject.
- Other server fixtures (src/tests/_internal/server/conftest.py): `client` (httpx.AsyncClient over `ASGITransport(app=dstack._internal.server.main.app)`), `image_config_mock`, `test_log_storage`, `mock_gateway_connection`. Network is blocked by default: pytest addopts `--disable-socket --allow-hosts=127.0.0.1,localhost --allow-unix-socket` (pyproject.toml:117-122); pytest-env sets `DSTACK_SSHPROXY_API_TOKEN=test-token`, `DSTACK_CLI_RICH_FORCE_TERMINAL=0`.
- Running tests (CONTRIBUTING.md:49-64): `uv run pytest src/tests`; `uv run pytest src/tests --runpostgres` for Postgres. CI (build-artifacts.yml:93) runs `uv run pytest -n auto src/tests --runui $RUNPOSTGRES`. Custom options defined in src/tests/conftest.py: `--runui`, `--runpostgres`; markers `ui`, `postgres`, `windows`, `windows_only` (+ `shim_version`, `dockerized` in pyproject).

## 5. Linting / type-checking

- ruff (pyproject.toml:84-96): `target-version = "py310"`, `line-length = 99`, lint select `["E","F","I","Q","W","PGH","FLY","S113"]`, ignore `["E501","E712"]`, isort `known-first-party = ["dstack"]`. Pinned `ruff==0.12.7` in dev group ("should match .pre-commit-config.yaml"); pre-commit hooks `ruff` + `ruff-format` from astral-sh/ruff-pre-commit. Commands per CONTRIBUTING.md: `uv run ruff check --fix` then `uv run ruff format`.
- pyright (pyproject.toml:98-113): `typeCheckingMode = "standard"`; `include` is a whitelist — `src/dstack/plugins`, `src/dstack/_internal/server`, `src/dstack/_internal/core/services`, backends aws/kubernetes/runpod, cli configurators/commands, and `src/tests/_internal/server/background/pipeline_tasks`; ignores `src/dstack/_internal/server/migrations/versions`. CI runs `jakebailey/pyright-action@v3` after `uv sync --all-extras` (build-artifacts.yml:74-79). Local: `uv tool install pyright && pyright -p .` (DEVELOPMENT.md). No mypy.
- requires-python `>=3.10`; pydantic is v1 (`pydantic>=1.10.10,<2.0.0` + `pydantic-duality>=1.2.4`).

## 6. Optional dependencies / extras (pyproject.toml:172-271)

- Base `[project.dependencies]` is the lightweight CLI/client set (pyyaml, requests, paramiko, rich, pydantic v1, gpuhunt, apscheduler<4, ...). Build backend: hatchling.
- `[project.optional-dependencies]`: `gateway` (fastapi/starlette/uvicorn/httpx/jinja2/aiorwlock/aiocache), `server` (fastapi, starlette, uvicorn[standard], sqlalchemy[asyncio]>=2.0.0, sqlalchemy_utils, alembic>=1.16.0, aiosqlite, asyncpg, alembic-postgresql-enum, sentry-sdk[fastapi], prometheus-client, grpcio, protobuf, smg-grpc-proto==0.4.9, docker, python-dxf, httpx, jinja2, watchfiles, requests-unixsocket, python-json-logger), then per-backend extras that each depend on `dstack[server]`: `aws` (boto3/botocore), `azure`, `gcp`, `datacrunch`, `verda`, `kubernetes`, `lambda`, `oci`, `nebius`, `fluentbit` (fluent-logger + elasticsearch), `crusoe` (server only), and `all = dstack[gateway,server,aws,azure,gcp,verda,kubernetes,lambda,nebius,oci,crusoe,fluentbit]`. Dev tooling is in `[dependency-groups] dev` (pytest~=8.0, pytest-asyncio, pytest-xdist, freezegun, testcontainers, openai>=1.68.2 which is dev-only for gateway/OpenAI-compat tests, ruff, ...) — installed via `uv sync --all-extras` (installs extras + dev group).
- Runtime guard pattern for optional imports — module-level availability flag, class defined only when import succeeds (src/dstack/_internal/server/services/storage/s3.py:5-13):
  ```python
  BOTO_AVAILABLE = True
  try:
      import botocore.exceptions
      from boto3 import Session
  except ImportError:
      BOTO_AVAILABLE = False
  else:
      class S3Storage(BaseStorage): ...
  ```
  Same pattern in services/storage/gcs.py, services/logs/aws.py, services/logs/gcp.py, services/logs/fluentbit.py, services/plugins.py. An `anthropic` extra would follow this: new extra in [project.optional-dependencies] depending on `dstack[server]`, guarded import + availability flag, and inclusion in `all`. **No anthropic/openai runtime dependency currently exists in project dependencies or extras** (openai appears only in the dev group).

## Gotchas
1) `src/dstack/_internal/server/testing/factories.py` DOES NOT EXIST — factories are in `testing/common.py`; importing "factories" would be a hallucination. 2) Tests create schema via `BaseModel.metadata.create_all`, NOT alembic — a new model works in tests without a migration, so a missing migration won't fail unit tests; the migration must still be authored for real deployments. 3) Migrations must be multi-replica/zero-downtime safe (expand-and-contract; only one table altered per migration; concurrent index creation with if_exists pre-drop) per contributing/MIGRATIONS.md — a naive autogenerated migration may violate this. 4) pytest runs with `--disable-socket` (only localhost allowed) — any Anthropic API client code in tests must be fully mocked, no network. 5) pytest-asyncio is in strict mode: every async test needs `@pytest.mark.asyncio`; Postgres coverage requires `@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)` and is skipped without `--runpostgres`. 6) pydantic is v1 (<2.0.0) with pydantic-duality — do not plan pydantic v2 APIs (`model_dump`, `field_validator`); persisted specs use `.json()`/`.parse_raw()`. 7) There is no JSON column type in models.py — structured data goes in `Text` columns as pydantic JSON. 8) Feature flags live in `dstack._internal.settings.FeatureFlags` (DSTACK_FF_*), not server/settings.py, and are auto-disabled in all tests by an autouse fixture — tests of a flag must monkeypatch FeatureFlags. 9) pyright only checks whitelisted paths (include list) — new dirs under `_internal/server` are covered automatically, but new test dirs are NOT unless added (only `src/tests/_internal/server/background/pipeline_tasks` is type-checked today). 10) `settings.py` env vars must be documented in `mkdocs/docs/reference/env.md` (settings.py module docstring says so; some defaults note 'keep in sync' with that doc). 11) Alembic autogenerate must be run from `src/dstack/_internal/server/` (alembic.ini lives there); revision files are placed in a year subdirectory automatically by file_template. 12) New pipeline-style tables need PipelineModelMixin columns + `last_processed_at` + a partial `ix_<table>_pipeline_fetch_q` index with BOTH `postgresql_where` and `sqlite_where`. 13) The `anthropic` package is not a dependency anywhere; `openai` exists only in the dev dependency group — an Anthropic SDK dep should be added as a new optional extra depending on dstack[server] with a try/except ImportError guard (S3Storage pattern).
