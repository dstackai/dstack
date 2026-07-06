# background-loop

## Summary
dstack's server background processing has two families, both started from the FastAPI lifespan in src/dstack/_internal/server/app.py (lines 178-184, gated by settings.SERVER_BACKGROUND_PROCESSING_ENABLED): (1) "pipeline tasks" — per-DB-model fetch/worker/heartbeat pipelines (background/pipeline_tasks/base.py) that claim rows with durable DB lock columns (lock_expires_at/lock_token/lock_owner) plus SELECT ... FOR UPDATE SKIP LOCKED, and (2) "scheduled tasks" — APScheduler IntervalTrigger jobs for infrequent, idempotent work. Multi-replica safety comes from the lock columns (not in-memory locks): a replica heartbeats lock_expires_at forward every ~1s while processing, and every mutation is guarded by `WHERE id = :id AND lock_token = :token`; if a replica dies, the lock expires and another replica's fetcher (which selects rows with `lock_expires_at IS NULL OR lock_expires_at < now`, ordered by last_processed_at ASC) takes over with a new token. Long-running work (instance provisioning, 10-55 min) is handled by (a) indefinite heartbeat extension during one `process()` call and (b) chunking across pipeline iterations via a status state machine (PENDING -> PROVISIONING -> per-iteration readiness checks against a deadline). A new `process_endpoints` task should be a new `EndpointPipeline` copied from the VolumePipeline skeleton (the simplest single-model example), registered in PipelineManager, with an EndpointModel using PipelineModelMixin + last_processed_at + a partial fetch index and an alembic migration.

## Key files
- src/dstack/_internal/server/background/pipeline_tasks/base.py — Pipeline, Fetcher, Worker, Heartbeater, PipelineItem, PipelineModel, ItemUpdateMap, NOW_PLACEHOLDER, set_unlock_update_map_fields, set_processed_update_map_fields, resolve_now_placeholders, log_lock_token_mismatch, log_lock_token_changed_after_processing, log_lock_token_changed_on_reset — The generic pipeline framework every processing task follows; 483 lines, fully read.
- src/dstack/_internal/server/background/pipeline_tasks/__init__.py — PipelineManager, PipelineHinter, get_pipeline_manager, start_pipeline_tasks, PipelineManager.register_pipeline — Where a new EndpointPipeline must be registered (builtin list at lines 35-48).
- src/dstack/_internal/server/background/pipeline_tasks/volumes.py — VolumePipeline, VolumeFetcher.fetch, VolumeWorker.process, _refetch_locked_volume, _apply_process_result, _VolumeUpdateMap, _ProcessResult — Cleanest single-model pipeline; the recommended template for process_endpoints (SUBMITTED->ACTIVE/FAILED via backend calls).
- src/dstack/_internal/server/background/pipeline_tasks/runs/__init__.py — RunPipeline, RunFetcher.fetch, RunWorker.process, _lock_related_jobs, _unlock_related_jobs, _reset_run_lock_for_retry — Example of cross-model child-row locking (run locks its jobs with the same lock_token) and per-status dispatch.
- src/dstack/_internal/server/background/pipeline_tasks/fleets.py — FleetPipeline, FleetFetcher.fetch, _lock_fleet_instances_for_processing, _apply_process_result — Second cross-model locking example; also shows exponential consolidation retry delays pattern (_CONSOLIDATION_RETRY_DELAYS).
- src/dstack/_internal/server/services/locking.py — get_locker(dialect_name), ResourceLocker, InMemoryResourceLocker, DummyResourceLocker, advisory_lock_ctx, try_advisory_lock_ctx, string_to_lock_id — In-memory lockset for SQLite, no-op dummy for Postgres; Postgres advisory locks for one-off critical sections. NOT the multi-replica mechanism for row processing.
- src/dstack/_internal/server/models.py — PipelineModelMixin (lines 204-207), RunModel (405), VolumeModel (951), ix_runs_pipeline_fetch_q index (464-472) — lock_expires_at/lock_token/lock_owner mixin + per-model last_processed_at + partial fetch index; EndpointModel must replicate this.
- src/dstack/_internal/server/background/scheduled_tasks/__init__.py — start_scheduled_tasks, get_scheduler, AsyncIOScheduler — APScheduler interval/date jobs; per-replica, no cross-replica dedup; for infrequent idempotent work only.
- src/dstack/_internal/server/services/pipelines.py — PipelineHinterProtocol, get_pipeline_hinter — FastAPI dependency for API handlers to hint fetchers after submitting a row (reduces processing latency).
- src/dstack/_internal/server/app.py — lifespan (start_scheduled_tasks/start_pipeline_tasks at 178-184, shutdown/drain at 206-214, default ThreadPoolExecutor at 123-124) — Startup/shutdown wiring; app.state.pipeline_manager set at line 181.
- src/dstack/_internal/server/db.py — get_db, get_session_ctx, get_session, Database.dialect_name, is_db_sqlite, is_db_postgres, sqlite_commit — Session helpers used by all fetchers/workers; get_session_ctx commits on clean exit; autoflush disabled.
- src/dstack/_internal/server/settings.py — SERVER_BACKGROUND_PROCESSING_ENABLED/DISABLED (47-50), SERVER_EXECUTOR_MAX_WORKERS (52), MAX_OFFERS_TRIED (54) — Only env vars controlling background processing; no per-pipeline tuning env vars exist.
- src/dstack/_internal/server/migrations/versions/2026/06_19_0709_857d8fa7fcc5_add_gateway_replica_pipeline.py — upgrade/downgrade — Most recent 'add a pipeline' migration: adds lock columns + status + last_processed_at, backfills last_processed_at=created_at. Template for endpoints migration.
- src/dstack/_internal/server/background/pipeline_tasks/instances/cloud_provisioning.py — offers loop capped by settings.MAX_OFFERS_TRIED (line 121), compute.create_instance via run_async (172) — Long-running (minutes) process() example, kept alive by heartbeater.
- src/dstack/_internal/server/background/scheduled_tasks/idle_volumes.py — process_idle_volumes — Scheduled-task skeleton: lockset + FOR UPDATE SKIP LOCKED + respects pipeline rows via lock_expires_at IS NULL.
- src/tests/_internal/server/background/pipeline_tasks/test_volumes.py — TestVolumeFetcher, fetcher/worker fixtures, _volume_to_pipeline_item — Test conventions: instantiate Fetcher/Worker with Mock queue/heartbeater, parametrize test_db over ['sqlite','postgres'].

## Details
All paths relative to /Users/dstack/dstack. Everything below was read from the working tree (branch master, commit 28ea5f86f era).

## 1. Two background-task families and how they start

`src/dstack/_internal/server/app.py` lifespan:
- line 123-124: `server_executor = ThreadPoolExecutor(max_workers=settings.SERVER_EXECUTOR_MAX_WORKERS)`; `asyncio.get_running_loop().set_default_executor(server_executor)` — this is the pool `run_async` uses.
- lines 176-184:
```python
if settings.SERVER_BACKGROUND_PROCESSING_ENABLED:
    scheduler = start_scheduled_tasks()
    pipeline_manager = start_pipeline_tasks()
    app.state.pipeline_manager = pipeline_manager
...
PROBES_SCHEDULER.start()  # separate AsyncIOScheduler for probes, started unconditionally
```
- shutdown (206-214): `pipeline_manager.shutdown()` → `scheduler.shutdown()` → `await pipeline_manager.drain()`.

### pipeline_tasks (`background/pipeline_tasks/__init__.py`)
`start_pipeline_tasks() -> PipelineManager` (line 106) docstring: "Start tasks processed by fetch-workers pipelines based on db + in-memory queues. Suitable for tasks that run frequently and need to lock rows for a long time."

`PipelineManager.__init__` (lines 31-49) instantiates and registers 12 builtin pipelines, each constructed as `XxxPipeline(pipeline_hinter=self._hinter)`: ComputeGroupPipeline, FleetPipeline, GatewayPipeline, GatewayReplicaPipeline, JobSubmittedPipeline, JobRunningPipeline, JobTerminatingPipeline, InstancePipeline, PlacementGroupPipeline, RunPipeline, ServiceRouterWorkerSyncPipeline, VolumePipeline. Public `register_pipeline(pipeline)` (line 51) appends and registers with the hinter — this is where `EndpointPipeline` gets added.

`PipelineHinter` (lines 80-93): `_hint_fetch_map: dict[str, list[Pipeline]]` keyed by `pipeline.hint_fetch_model_name` (a `Model.__name__` string, e.g. `"VolumeModel"`); `hint_fetch(model_name)` calls `pipeline.hint_fetch()` on all pipelines registered for that model (all three job pipelines share `JobModel.__name__`). Singleton via `get_pipeline_manager()` (line 99).

API handlers obtain the hinter via `get_pipeline_hinter(request: Request) -> PipelineHinterProtocol` in `src/dstack/_internal/server/services/pipelines.py:22` (reads `request.app.state.pipeline_manager`, returns a no-op hinter if background processing is disabled). Real usages: `services/volumes.py:317 pipeline_hinter.hint_fetch(VolumeModel.__name__)` after volume create; `services/runs/__init__.py:825-826, 906`; `services/fleets.py:880, 1112-1113`; `services/gateways/__init__.py:291`. Hints are local-replica only (they just set an asyncio.Event on the fetcher).

### scheduled_tasks (`background/scheduled_tasks/__init__.py`)
`start_scheduled_tasks() -> AsyncIOScheduler` (line 37) docstring: "Start periodic tasks triggered by apscheduler at specific times/intervals. Suitable for tasks that run infrequently and don't need to lock rows for a long time." Jobs (lines 43-60): `init_gateways_in_background` (DateTrigger, once), `preload_offers_catalog` (DateTrigger + IntervalTrigger(minutes=10)), `process_probes` (seconds=3, jitter=1), `collect_metrics` (10s), `delete_metrics` (5m), `delete_events` (7m), `process_gateways_connections` (15s), `process_idle_volumes` (60s, jitter=10), `delete_instance_healthchecks` (5m), plus prometheus pair if `settings.ENABLE_PROMETHEUS_METRICS`. `max_instances=1` on most — note this is per-process only, NOT cross-replica; every replica runs every scheduled task, so they must be idempotent (e.g. `delete_events` is a bare `DELETE WHERE recorded_at < cutoff`, scheduled_tasks/events.py:13-17).

## 2. The pipeline framework (base.py) — exact skeleton

`background/pipeline_tasks/base.py`:

```python
@dataclass
class PipelineItem:              # base.py:34
    __tablename__: str
    id: uuid.UUID
    lock_expires_at: datetime
    lock_token: uuid.UUID
    prev_lock_expired: bool      # set by fetchers, currently consumed nowhere (verified by grep)

class PipelineModel(Protocol):   # base.py:50 — model must have:
    __tablename__: str; __mapper__; __table__
    id: Mapped[uuid.UUID]
    lock_expires_at: Mapped[Optional[datetime]]
    lock_token: Mapped[Optional[uuid.UUID]]

class Pipeline(Generic[ItemT], ABC):   # base.py:67
    def __init__(self, workers_num, queue_lower_limit_factor, queue_upper_limit_factor,
                 min_processing_interval: timedelta, lock_timeout: timedelta,
                 heartbeat_trigger: timedelta) -> None: ...
    def start(self): ...      # creates asyncio tasks: heartbeater.start(), each worker.start(), fetcher.start()
    def shutdown(self): ...   # stop flags + cancel tasks
    async def drain(self): ...
    def hint_fetch(self): self._fetcher.hint()
    # abstract: hint_fetch_model_name (property str), _heartbeater, _fetcher, _workers
```
Queue sizing: `_queue_desired_minsize = ceil(workers_num * queue_lower_limit_factor)`, `_queue_maxsize = ceil(workers_num * queue_upper_limit_factor)`; `asyncio.Queue[ItemT](maxsize=_queue_maxsize)`.

`Fetcher` (base.py:257): loop — if `qsize >= desired_minsize` sleep `queue_check_delay=1.0`; else `items = await self.fetch(limit=maxsize - qsize)`; on empty fetch, wait on `self._fetch_event` with timeout from `_DEFAULT_FETCH_DELAYS = [0.5, 1, 2, 5]` seconds indexed by consecutive-empty count, ±20% jitter, with a 10% random chance of resetting to the minimal delay (base.py:326-337); `hint()` sets the event. Non-empty: `queue.put_nowait(item)` + `heartbeater.track(item)`. Abstract: `async def fetch(self, limit: int) -> list[ItemT]`.

`Worker` (base.py:340): `__init__(queue, heartbeater, pipeline_hinter: PipelineHinterProtocol)`; loop: `item = await queue.get()`; `await self.process(item)` inside try/except-log; `finally: await self._heartbeater.untrack(item)`. Abstract: `async def process(self, item: ItemT)`.

`Heartbeater` (base.py:166): `__init__(model_type: type[PipelineModel], lock_timeout, heartbeat_trigger, heartbeat_delay: float = 1.0)`. Every ~1s: for each tracked item, if `lock_expires_at < now` → untrack + warn ("Failed to heartbeat ... in time"); if `lock_expires_at < now + heartbeat_trigger` → include in one bulk `UPDATE model SET lock_expires_at = now + lock_timeout WHERE (id==i.id AND lock_token==i.lock_token) OR ... RETURNING id` (base.py:227-240); items whose token changed are untracked. So a lock is extended indefinitely while the replica is alive and the worker is still processing — this is what makes minutes-long `process()` calls safe.

Update-map helpers (base.py:379-483): `NOW_PLACEHOLDER` + `resolve_now_placeholders(update_values, now)` so all timestamps in one apply-transaction share the same `now`; `ItemUpdateMap` TypedDict with `lock_expires_at/lock_token/lock_owner/last_processed_at`; `set_unlock_update_map_fields(m)` sets the three lock fields to None; `set_processed_update_map_fields(m, now=NOW_PLACEHOLDER)` sets `last_processed_at`; standard warn-loggers `log_lock_token_mismatch(logger, item, action="process")`, `log_lock_token_changed_after_processing(logger, item, ...)`, `log_lock_token_changed_on_reset(logger)`.

## 3. Model-side requirements

`src/dstack/_internal/server/models.py`:
```python
class PipelineModelMixin:                                   # models.py:204
    lock_expires_at: Mapped[Optional[datetime]] = mapped_column(NaiveDateTime)
    lock_token: Mapped[Optional[uuid.UUID]] = mapped_column(UUIDType(binary=False))
    lock_owner: Mapped[Optional[str]] = mapped_column(String(100))
```
Models using it: RunModel(405), ServiceRouterWorkerSyncModel(475), JobModel(506), GatewayModel(600), GatewayComputeModel(656), FleetModel(754), InstanceModel(805), VolumeModel(951), PlacementGroupModel(1011), ComputeGroupModel(1047).

Each pipeline-processed model also declares its own `last_processed_at: Mapped[datetime] = mapped_column(NaiveDateTime)` (non-null) and a partial index for the fetch query, e.g. RunModel (models.py:464-472):
```python
Index("ix_runs_pipeline_fetch_q", last_processed_at.asc(),
      postgresql_where=status.not_in(RunStatus.finished_statuses()),
      sqlite_where=status.not_in(RunStatus.finished_statuses()))
```
New rows are created with `last_processed_at` = submission time (`services/runs/__init__.py:744 last_processed_at=submitted_at`; `services/volumes.py:307 last_processed_at=now`); fetchers treat `last_processed_at == created_at` (or `== submitted_at` for runs) as "never processed → skip the min-interval gate". Some models additionally have `skip_min_processing_interval: Mapped[bool]` (RunModel:432, JobModel, InstanceModel) which fetchers OR into the interval condition and reset to False on fetch.

Migration template: `migrations/versions/2026/06_19_0709_857d8fa7fcc5_add_gateway_replica_pipeline.py` — batch_alter_table adds `last_processed_at` (NaiveDateTime), `status`, `status_message`, `lock_expires_at`, `lock_token` (UUIDType(binary=False)), `lock_owner` (String(100)); backfills `last_processed_at = created_at`; then makes columns non-null. Migrations live under `src/dstack/_internal/server/migrations/versions/<year>/`.

## 4. Standard fetch skeleton (verified in VolumeFetcher.fetch, volumes.py:135-196; same shape in runs/fleets/instances)

```python
volume_lock, _ = get_locker(get_db().dialect_name).get_lockset(VolumeModel.__tablename__)
async with volume_lock:                       # asyncio.Lock on SQLite; DummyAsyncLock (no-op) on Postgres
    async with get_session_ctx() as session:
        now = get_current_datetime()
        res = await session.execute(
            select(VolumeModel)
            .where(
                or_(VolumeModel.status == VolumeStatus.SUBMITTED, VolumeModel.to_be_deleted == True),
                VolumeModel.deleted == False,
                or_(VolumeModel.last_processed_at <= now - self._min_processing_interval,
                    VolumeModel.last_processed_at == VolumeModel.created_at),
                or_(VolumeModel.lock_expires_at.is_(None), VolumeModel.lock_expires_at < now),
                or_(VolumeModel.lock_owner.is_(None), VolumeModel.lock_owner == VolumePipeline.__name__),
            )
            .order_by(VolumeModel.last_processed_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True, key_share=True, of=VolumeModel)
            .options(load_only(VolumeModel.id, VolumeModel.lock_token, VolumeModel.lock_expires_at, ...)))
        volume_models = list(res.scalars().all())
        lock_expires_at = get_current_datetime() + self._lock_timeout
        lock_token = uuid.uuid4()               # ONE token per fetched batch
        for m in volume_models:
            prev_lock_expired = m.lock_expires_at is not None
            m.lock_expires_at = lock_expires_at; m.lock_token = lock_token
            m.lock_owner = VolumePipeline.__name__
            items.append(VolumePipelineItem(__tablename__=VolumeModel.__tablename__, id=m.id, ...))
        await session.commit()
return items
```
Fetchers are decorated `@sentry_utils.instrument_pipeline_task("VolumeFetcher.fetch")` (workers likewise with `"VolumeWorker.process"`); `instrument_pipeline_task(name)` / `instrument_scheduled_task(f)` live in `server/utils/sentry_utils.py:14-19`.

## 5. Standard worker skeleton (VolumeWorker.process, volumes.py:212-291)

1. Refetch with full relationships: `select(VolumeModel).where(VolumeModel.id == item.id, VolumeModel.lock_token == item.lock_token).options(joinedload(...))` → `scalar_one_or_none()`; if None → `log_lock_token_mismatch(logger, item)`; return.
2. Do the actual processing as pure-ish functions returning a `_ProcessResult` containing a TypedDict update map (`_VolumeUpdateMap(ItemUpdateMap)` adds `status`, `status_message`, `volume_provisioning_data`, `deleted`, `deleted_at`). Blocking backend/SDK calls go through `run_async` (`src/dstack/_internal/utils/common.py:49-51`: `await asyncio.get_running_loop().run_in_executor(None, partial(func, *args, **kwargs))` — the default executor is the 128-thread pool from app.py:123).
3. Apply: `set_processed_update_map_fields(update_map)`; `set_unlock_update_map_fields(update_map)`; `resolve_now_placeholders(update_map, now=get_current_datetime())`; then
```python
res = await session.execute(
    update(VolumeModel)
    .where(VolumeModel.id == volume_model.id, VolumeModel.lock_token == volume_model.lock_token)
    .values(**update_map).returning(VolumeModel.id))
if len(list(res.scalars().all())) == 0:
    log_lock_token_changed_after_processing(logger, item); return
```
plus event emission (`services.events.emit(session, msg, actor=events.SystemActor(), targets=[events.Target.from_model(model)])` and per-domain `emit_*_status_change_event`).

## 6. Cross-model (child row) locking — runs and fleets

`RunPipeline._lock_related_jobs` (runs/__init__.py:763-810): under the jobs lockset lock, `select(JobModel).where(JobModel.run_id == item.id, status not in JOB_STATUSES_EXCLUDED_FOR_LOCKING, lock free or expired, lock_owner NULL or == RunPipeline.__name__).order_by(JobModel.id).with_for_update(skip_locked=True, key_share=True, of=JobModel)`; then re-selects ALL current eligible job ids — if the locked set != full set, it gives up: `_reset_run_lock_for_retry` (runs/__init__.py:813-835) which keeps `lock_owner` (so the row stays owned by the pipeline and other subsystems stay away), but sets `lock_expires_at=None, lock_token=None, last_processed_at=now` so the item is retried on a later fetch and the heartbeater can no longer touch it. Children get the parent's `lock_expires_at/lock_token` and `lock_owner=RunPipeline.__name__`. On every apply/noop path, `_unlock_related_jobs` (950-969) nulls the three lock columns `WHERE id IN locked AND lock_token == item.lock_token AND lock_owner == RunPipeline.__name__`. FleetPipeline does the same for InstanceModel (`fleets.py:374-445`, unlock at 762-779), and InstanceFetcher avoids fighting the fleet by requiring `FleetModel.lock_owner IS NULL` for instances in a fleet (instances/__init__.py:212-224).

Related: run/fleet workers unlock/update parent + children in ONE transaction; job update rows are built with `set_unlock_update_map_fields`/`set_processed_update_map_fields` per row and executed as bulk `await session.execute(update(JobModel), job_update_rows)` (runs/__init__.py:588-589).

## 7. Locking service — exact API (`src/dstack/_internal/server/services/locking.py`)

- `get_locker(dialect_name: str) -> ResourceLocker` (line 175): returns module-level `InMemoryResourceLocker` for `"sqlite"`, else `DummyResourceLocker` ("We could use an in-memory locker on Postgres but it can lead to unnecessary lock contention, so we use a dummy locker that does not take any locks."). NOTE: it takes `dialect_name` as a required arg — call sites are all `get_locker(get_db().dialect_name)`.
- `ResourceLocker.get_lockset(namespace: str) -> tuple[LocksetLock, Lockset]` — a guard lock plus a set of locked keys; `lock_ctx(namespace, keys)` acquires all keys (keys must be sorted to avoid deadlock; implemented by `_wait_to_lock_many(lock, locked, keys, delay=0.1)`).
- `string_to_lock_id(s) -> int` (sha256 mod 2**63); `advisory_lock_ctx(bind, dialect_name, resource)` (line 125) — `pg_advisory_lock`/`pg_advisory_unlock`, NO-OP on SQLite, with documented footguns (must release on the same connection; don't commit inside when bind is an AsyncSession); `try_advisory_lock_ctx` (line 156) yields a bool. Used for `migrate()` (db.py:83) and `server_init` (app.py:140).

**How multi-replica double-processing is actually prevented for pipelines**: not by the locker. It's (a) the durable `lock_expires_at`/`lock_token`/`lock_owner` columns claimed in the fetch transaction, (b) `WITH FOR UPDATE SKIP LOCKED` making concurrent Postgres fetch transactions skip each other's rows mid-claim, and (c) every subsequent write being conditioned on `lock_token`. On SQLite (single replica by definition) `with_for_update` is a no-op and the in-memory lockset lock serializes fetchers/scheduled-task claimers within the process instead.

## 8. Replica death / stale lock recovery

If a replica dies mid-processing: heartbeats stop → `lock_expires_at` (20-40s in the future) passes → any replica's fetcher matches the row again via `or_(lock_expires_at.is_(None), lock_expires_at < now)` and issues a NEW `lock_token`; `prev_lock_expired=True` is recorded on the item (currently informational only). If the dead replica's worker somehow finishes later, its `UPDATE ... WHERE lock_token == old_token` matches 0 rows and is logged, not applied. There is no separate reaper/janitor; recovery latency ≈ remaining lock_timeout. `ORDER BY last_processed_at ASC` guarantees stalest-first pickup. If `process()` raises, the Worker logs and unt racks; the row simply stays locked until expiry (retry latency ≈ lock_timeout).

## 9. Long-running operations (minutes+)

Two mechanisms, both exemplified by instances:
1. **Heartbeat-extended single call**: `InstancePipeline` PENDING processing (instances/cloud_provisioning.py) loops over offers, each `compute.create_instance` executed via `run_async` (line 172), loop capped by `settings.MAX_OFFERS_TRIED` (line 121, default 25, "Limit number of offers tried to prevent long-running processing in case all offers fail"). The Heartbeater keeps extending the row lock every ~1s check for as long as needed. `JobSubmittedPipeline` similarly calls `run_async(compute...)` at jobs_submitted.py:1816, 2287, 2309.
2. **Chunked state machine across iterations**: after `create_instance` returns, the worker only writes `status=PROVISIONING` + `job_provisioning_data` + `started_at=NOW_PLACEHOLDER` and unlocks (cloud_provisioning.py:208-231). Each subsequent pipeline iteration (~min_processing_interval) re-picks the PROVISIONING row and checks readiness against `get_provisioning_deadline` (instances/check.py:200-204, 297-301), with per-backend timeouts from `get_provisioning_timeout(backend_type, instance_type_name)` in `background/pipeline_tasks/common.py:6` (10 min default, up to 55 min for Vultr bare metal). **This is the pattern to copy for an endpoint LLM-agent flow: persist per-phase status (e.g. SUBMITTED → PROVISIONING/DEPLOYING → health-checking) so each `process()` is resumable if a replica dies, rather than one hours-long process() call.**

## 10. Pipeline tuning defaults (constructor kwargs; no env vars)

| Pipeline | workers_num | min_processing_interval | lock_timeout | heartbeat_trigger |
|---|---|---|---|---|
| RunPipeline (runs/__init__.py:56) | 10 | 5s (x2 for non SUBMITTED/TERMINATING) | 30s | 15s |
| JobSubmittedPipeline (jobs_submitted.py:158) | 40 | 4s | 40s | 20s |
| JobRunningPipeline (jobs_running.py:138) | 20 | 5s | 30s | 15s |
| JobTerminatingPipeline (jobs_terminating.py:91) | 20 | 2s | 30s | 15s |
| InstancePipeline (instances/__init__.py:81) | 20 | 7s (x2 for idle/busy) | 30s | 15s |
| FleetPipeline (fleets.py:69) | 10 | 15s | 20s | 10s |
| VolumePipeline (volumes.py:61) | 10 | 15s | 30s | 15s |
| GatewayPipeline (gateways.py:62) | 10 | 15s | 30s | 15s |
| GatewayReplicaPipeline (gateway_replicas.py:56) | 10 | 15s | 30s | 15s |
| ComputeGroupPipeline (compute_groups.py:49) | 10 | 15s | 30s | 15s |
| PlacementGroupPipeline (placement_groups.py:46) | 10 | 15s | 30s | 15s |
| ServiceRouterWorkerSyncPipeline (service_router_worker_sync.py:54) | 8 | 5s | 25s | 10s |
All use queue_lower_limit_factor=0.5, queue_upper_limit_factor=2.0.

## 11. Settings / env vars (server/settings.py)

- `DSTACK_SERVER_BACKGROUND_PROCESSING_DISABLED` → `SERVER_BACKGROUND_PROCESSING_DISABLED/ENABLED` (lines 47-50) — the only kill switch; disables BOTH scheduled and pipeline tasks (app.py:178).
- `DSTACK_SERVER_EXECUTOR_MAX_WORKERS` (line 52, default 128) — thread pool for `run_async`.
- `DSTACK_SERVER_MAX_OFFERS_TRIED` (line 54, default 25).
- `DSTACK_DB_POOL_SIZE` (44, default 20) / `DSTACK_DB_MAX_OVERFLOW` (45, default 20).
- `DSTACK_ENABLE_PROMETHEUS_METRICS` gates the prometheus scheduled tasks.
There are NO env vars for per-pipeline workers/intervals/lock timeouts — constructor defaults only.

## 12. Scheduled-task skeleton (if endpoints ever needed one)

`process_idle_volumes` (scheduled_tasks/idle_volumes.py:24-63): decorated `@sentry_utils.instrument_scheduled_task`; gets `(lock, lockset) = get_locker(get_db().dialect_name).get_lockset(VolumeModel.__tablename__)`; under `async with lock:` selects candidate ids with `.where(..., VolumeModel.lock_expires_at.is_(None), VolumeModel.id.not_in(lockset)).limit(10).with_for_update(skip_locked=True, key_share=True)` and adds ids to the lockset; processes; `finally: lockset.difference_update(volume_ids)`. Note it defers real work to the pipeline by setting `to_be_deleted=True`. The `lock_expires_at.is_(None)` check is how a scheduled task avoids touching rows a pipeline currently holds.

## 13. Precise recipe for a `process_endpoints` pipeline task

1. **Model**: `class EndpointModel(PipelineModelMixin, BaseModel)` in `src/dstack/_internal/server/models.py` with `id UUIDType(binary=False) pk default uuid4`, `created_at`, `last_processed_at: Mapped[datetime] = mapped_column(NaiveDateTime)` (init to created_at on insert), `status` (use `EnumAsString(EndpointStatus, 100)`), `status_message`, `deleted: Mapped[bool]`, FKs to projects/users, and `__table_args__ = (Index("ix_endpoints_pipeline_fetch_q", last_processed_at.asc(), postgresql_where=<active-status filter>, sqlite_where=<same>),)`.
2. **Migration**: alembic revision under `src/dstack/_internal/server/migrations/versions/2026/`, modeled on `857d8fa7fcc5` (or a plain create_table since it's a new table).
3. **Pipeline**: `src/dstack/_internal/server/background/pipeline_tasks/endpoints.py` with `EndpointPipelineItem(PipelineItem)` (+ `status` field), `EndpointPipeline(Pipeline[EndpointPipelineItem])` (copy VolumePipeline verbatim: __init__ wires `Heartbeater(model_type=EndpointModel, ...)`, `EndpointFetcher`, N× `EndpointWorker`; `hint_fetch_model_name -> EndpointModel.__name__`; expose `_heartbeater/_fetcher/_workers` via private-name properties), `EndpointFetcher.fetch` copying the section-4 query (status filter e.g. `status.in_([SUBMITTED, PROVISIONING, ...])`, `lock_owner IS NULL OR == EndpointPipeline.__name__`), `EndpointWorker.process` doing refetch-by-token → per-status dispatch → apply-with-token pattern. Suggested tuning for agent-driven provisioning: workers_num ~10, min_processing_interval 5-15s, lock_timeout 30s, heartbeat_trigger 15s (heartbeater makes multi-minute steps safe, but prefer chunking into statuses per section 9.2).
4. **Register** in `PipelineManager.__init__` builtin list (`background/pipeline_tasks/__init__.py:35-48`).
5. **Submit-side hint**: in the endpoint-create service function, accept `pipeline_hinter: PipelineHinterProtocol` (injected in the router via `Depends(get_pipeline_hinter)`, as `services/volumes.py` does) and call `pipeline_hinter.hint_fetch(EndpointModel.__name__)` after commit.
6. **Sub-resource**: if the endpoint pipeline must mutate its RunModel/service, follow the `_lock_related_jobs` pattern (claim child rows with same lock_token + lock_owner=EndpointPipeline.__name__, reset-own-lock-for-retry if children unavailable) — or better, avoid cross-pipeline row writes and interact with runs via the `services/runs` submit/terminate service functions the way API handlers do (cross-pipeline direct writes are only done for the benign `skip_min_processing_interval` flag, jobs_running.py:990-999).
7. **Tests**: `src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py`, mirroring `test_volumes.py`: fixtures constructing `EndpointFetcher(queue=asyncio.Queue(), queue_desired_minsize=1, ..., heartbeater=Mock())` and `EndpointWorker(queue=Mock(), heartbeater=Mock(), pipeline_hinter=Mock())`, `@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)`, helpers from `dstack._internal.server.testing.common`.

## Gotchas
1. STALE KNOWLEDGE TRAP: the old `process_runs.py`-style `@sentry_utils.instrument_background_task` + apscheduler-per-N-seconds processing modules do NOT exist anymore; runs/jobs/fleets/instances/volumes/gateways are all fetch/worker Pipelines under background/pipeline_tasks/. Also `get_locker()` now REQUIRES a dialect_name arg: `get_locker(get_db().dialect_name)`.
2. The in-memory lockset locker is NOT the multi-replica mechanism — on Postgres it's a no-op DummyResourceLocker by design. Cross-replica exclusion = lock_expires_at/lock_token/lock_owner columns + FOR UPDATE SKIP LOCKED in the fetch + token-guarded UPDATEs. Any plan that says "acquire the locker to be replica-safe" is wrong.
3. Every write after fetch MUST carry `WHERE lock_token == item.lock_token` and every terminal apply MUST both unlock (set_unlock_update_map_fields) and bump last_processed_at (set_processed_update_map_fields) in the SAME UPDATE; forgetting last_processed_at causes hot-looping, forgetting unlock stalls the row for lock_timeout.
4. `min_processing_interval` gating uses `last_processed_at == created_at` (or `== submitted_at` for runs) to fast-path brand-new rows — so the row-creation code must set last_processed_at equal to created_at, not leave it NULL (column is non-nullable).
5. APScheduler `max_instances=1` and DateTrigger init tasks are per-replica; scheduled tasks run concurrently on every replica and must be idempotent. Don't put endpoint provisioning there — use a pipeline (that's exactly what the two docstrings at pipeline_tasks/__init__.py:107-109 and scheduled_tasks/__init__.py:38-41 distinguish).
6. `hint_fetch` only wakes the local replica's fetcher; without it processing still happens within a few seconds via the polling fetch delays (max ~5s + jitter), so it's an optimization, not a correctness requirement.
7. Worker `process()` exceptions are swallowed+logged by Worker.start(); the row then stays locked until lock_expires_at passes (~lock_timeout retry latency). If a replica dies mid-process, work is re-picked from scratch after lock expiry — so the endpoint agent/deploy flow must be idempotent or persisted as a status state machine (see instances PENDING→PROVISIONING→deadline-checked pattern) rather than a single monolithic process() that runs for many minutes; the heartbeater technically allows unbounded process() duration, but crash-recovery restarts the whole step.
8. `run_async` uses the loop's default executor (ThreadPoolExecutor, 128 threads, app.py:123); long blocking calls (LLM API calls, SSH) should go through it or a native-async client, or they'll block heartbeats for the entire replica.
9. DB sessions: `get_session_ctx()` commits on clean exit, `expire_on_commit=False`, `autoflush=False` — mutations made on ORM objects during fetch are only persisted because fetch explicitly commits; in workers prefer explicit `update()` statements over ORM attribute mutation.
10. `prev_lock_expired` on PipelineItem is set by all fetchers but consumed nowhere — don't build logic assuming it does something.
11. `lock_owner` is a pipeline-name namespace: fetchers only take rows where lock_owner is NULL or their own class name, and the reset-for-retry path deliberately KEEPS lock_owner while nulling lock_expires_at/lock_token. If two subsystems (e.g. an endpoints pipeline and the run pipeline) can lock the same table, both must honor this filter.
12. Datetimes are stored via NaiveDateTime columns while `get_current_datetime()` returns tz-aware UTC — copy existing comparison patterns verbatim rather than mixing aware/naive by hand.
13. Background processing can be disabled entirely (DSTACK_SERVER_BACKGROUND_PROCESSING_DISABLED, used in tests); services must not assume the pipeline manager exists — `get_pipeline_hinter` already handles this with a no-op hinter.
