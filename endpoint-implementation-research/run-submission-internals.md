# run-submission-internals

## Summary
Server-side run creation is fully feasible from a background task: `dstack._internal.server.services.runs` (now a package at src/dstack/_internal/server/services/runs/) exposes `get_plan`, `apply_plan`, `submit_run`, `stop_runs`, `delete_runs`, and `get_run_by_name/-id` that take only (AsyncSession, UserModel, ProjectModel, RunSpec/plan) — no HTTP request context. Repo-less runs are first-class: leaving `run_spec.repo_id`/`repo_data` as None makes the server default to the virtual repo (id "none") and auto-create the RepoModel row; no code upload is needed. There is NO existing precedent of the server creating whole runs from background tasks (submit_run/apply_plan are only called from routers/runs.py), but the server does create replacement/scale-up JobModels in the RunPipeline (rolling deployments, retries, scheduled runs), and the run/job/instance state machines are driven entirely by the multi-replica-safe pipeline_tasks framework (row locks via lock_owner/lock_token/lock_expires_at + FOR UPDATE SKIP LOCKED). There is no dedicated system user; the closest is the startup-created "admin" user (`get_or_create_admin_user`), and UserModel stores an encrypted API token plus per-user SSH keypair (required for run submission). RunModel has no tags/labels column — linking an endpoint to its run must be done via run_name convention or an FK on the new endpoint table.

## Key files
- src/dstack/_internal/server/services/runs/__init__.py — get_plan, apply_plan, submit_run, stop_runs, delete_runs, get_run, get_run_by_name, get_run_by_id, get_run_model_by_name, run_model_to_run, switch_run_status, create_job_model_for_new_submission, is_job_ready, _generate_run_name, _get_run_repo_or_error — The whole server-side run lifecycle API. All functions take (session, user/project models, RunSpec) — callable from background tasks.
- src/dstack/_internal/server/services/runs/spec.py — validate_run_spec_and_set_defaults, check_can_update_run_spec, can_update_run_spec — Sets virtual-repo defaults (repo_id='none', VirtualRunRepoData) and requires ssh_key_pub or user.ssh_public_key.
- src/dstack/_internal/core/models/runs.py — RunSpec (l.522), RunStatus (l.652), RunTerminationReason (l.91), JobStatus (l.62), JobTerminationReason (l.134), Run (l.675), RunPlan (l.715), ApplyRunPlanInput (l.730), ServiceSpec (l.643) — Core pydantic models; RunStatus.finished_statuses() = [TERMINATED, FAILED, DONE].
- src/dstack/_internal/core/models/repos/virtual.py — DEFAULT_VIRTUAL_REPO_ID='none', VirtualRepoInfo, VirtualRunRepoData, VirtualRepo — Virtual (repo-less) repo mechanism.
- src/dstack/_internal/server/routers/runs.py — root_router /api/runs/list; project_router /api/project/{project_name}/runs/{get,get_plan,apply,stop,delete,submit(deprecated)} — The only place submit_run/apply_plan/stop_runs are invoked today; shows required call pattern incl. pipeline_hinter and ssh-key refresh.
- src/dstack/_internal/server/schemas/runs.py — GetRunPlanRequest, ApplyRunPlanRequest, StopRunsRequest, SubmitRunRequest — API request schemas.
- src/dstack/_internal/server/background/pipeline_tasks/runs/__init__.py — RunPipeline, RunFetcher, RunWorker — Multi-replica-safe processing pattern (lock_token/lock_expires_at/lock_owner + FOR UPDATE SKIP LOCKED) to copy for an EndpointPipeline.
- src/dstack/_internal/server/background/pipeline_tasks/runs/active.py — process_active_run, _get_active_run_transition, _analyze_active_run — Run status semantics: RUNNING if any replica job RUNNING; FAILED via TERMINATING+termination_reason; rolling deployment/scaling create JobModels here (server-side job creation precedent).
- src/dstack/_internal/server/background/pipeline_tasks/__init__.py — PipelineManager, PipelineHinter, start_pipeline_tasks, get_pipeline_manager — Where a new pipeline would be registered; started from app.py lifespan when SERVER_BACKGROUND_PROCESSING_ENABLED.
- src/dstack/_internal/server/services/services/__init__.py — register_service, _register_service_in_server, _register_service_in_gateway — Called synchronously inside submit_run for service runs; produces ServiceSpec url (/proxy/services/<project>/<run>/ or gateway URL) and model mapping.
- src/dstack/_internal/server/services/users.py — get_or_create_admin_user (l.45), create_user (l.160), get_user_model_by_name (l.327), refresh_ssh_key (l.232) — Identity options for a background task; users get RSA ssh keypair on creation; token stored encrypted.
- src/dstack/_internal/server/services/projects.py — get_project_model_by_name (l.572), get_project_model_by_name_or_error (l.589) — How to load ProjectModel (with backends+members joined) to act 'as' a project.
- src/dstack/_internal/server/models.py — RunModel (l.405), UserModel (l.210), PipelineModelMixin (l.204) — RunModel columns — no tags/labels column; UserModel.token is EncryptedString + token_hash.
- src/dstack/_internal/server/services/repos.py — create_or_update_repo (l.101), get_repo_model (l.317), get_code_model (l.331) — Virtual repo row auto-created by _get_run_repo_or_error during submit_run.
- src/dstack/api/_public/runs.py — RunCollection.get_run_plan (l.470), apply_plan (l.547), apply_configuration (l.585) — Client-side reference for how RunSpec is constructed for repo-less configs.
- src/dstack/_internal/cli/services/configurators/run.py — BaseRunConfigurator.apply_configuration (l.87), ServiceConfigurator (l.716) — CLI apply flow for services; falls back to init_default_virtual_repo when no repo.

## Details
# Ground truth: server-side run (service) creation, monitoring, termination

## 1. services/runs package (src/dstack/_internal/server/services/runs/)
Package files: `__init__.py` (1243 l.), `plan.py`, `replicas.py`, `spec.py`, `router_worker_sync.py`, `service_router_worker_sync.py`.

Exact signatures (all in `src/dstack/_internal/server/services/runs/__init__.py`):

- `async def get_plan(session: AsyncSession, project: ProjectModel, user: UserModel, run_spec: RunSpec, max_offers: Optional[int], legacy_repo_dir: bool = False) -> RunPlan` (l.528). Applies plugin policies, validates spec, computes `job_plans` via `get_job_plans` (runs/plan.py), detects `action` CREATE vs UPDATE. Optional step — NOT required before submit.
- `async def apply_plan(session: AsyncSession, user: UserModel, project: ProjectModel, plan: ApplyRunPlanInput, force: bool, pipeline_hinter: Optional[PipelineHinterProtocol] = None, legacy_repo_dir: bool = False) -> Run` (l.587). Applies plugin policies; if `run_spec.run_name is None` or no active run with that name → delegates to `submit_run`; else attempts in-place update (only fields in `_UPDATABLE_SPEC_FIELDS`/`_CONF_UPDATABLE_FIELDS`, spec.py:26-63), bumping `deployment_num` (rolling deployment for services).
- `async def submit_run(session: AsyncSession, user: UserModel, project: ProjectModel, run_spec: RunSpec, pipeline_hinter: Optional[PipelineHinterProtocol] = None) -> Run` (l.681). Flow: `validate_run_spec_and_set_defaults(user, run_spec)` → `_get_run_repo_or_error` (auto-creates virtual repo) → `get_project_secrets_mapping` → run-name lock (`pg_advisory_xact_lock` / lockset namespace `run_names_{project.name}`) → generate name if None (`_generate_run_name`, l.1134, adjective-animal-N) else `delete_runs` of finished same-name run → `_validate_run` (volumes) → creates `RunModel(...)` (l.734: initial_status=SUBMITTED, or PENDING+0 replicas if `merged_profile.schedule`; `desired_replica_count=1` — real value set by RunPipeline; `priority=run_spec.configuration.priority`; `deployment_num=0`) → for services: `await services.register_service(session, run_model, run_spec)` then per replica-group creates jobs via `get_jobs_from_run_spec(run_spec=..., secrets=..., replica_num=..., replica_group_name=...)` and `create_job_model_for_new_submission(run_model, job, status=JobStatus.SUBMITTED)` (l.833), plus `ensure_service_router_worker_sync_row(session, run_model, run_spec)` → `session.commit()` → `pipeline_hinter.hint_fetch("JobModel"/"RunModel")` if provided → returns `await get_run_by_id(...)`.
- `async def stop_runs(session: AsyncSession, user: UserModel, project: ProjectModel, runs_names: List[str], abort: bool, pipeline_hinter: Optional[PipelineHinterProtocol] = None)` (l.865). Sets `termination_reason = RunTerminationReason.ABORTED_BY_USER|STOPPED_BY_USER`, `switch_run_status(session, run_model, RunStatus.TERMINATING, actor=UserActor)`, `skip_min_processing_interval=True`; the RunPipeline finishes termination. Commits.
- `async def delete_runs(session, user, project, runs_names: List[str])` (l.909) — only finished runs; sets `deleted=True`.
- Reads: `async def get_run(session, project, run_name=None, run_id=None) -> Optional[Run]` (l.456); `get_run_model_by_name(session, project, run_name) -> Optional[RunModel]` (l.477); `get_run_by_name` (l.496); `get_run_by_id` (l.507); `def run_model_to_run(run_model, include_jobs=True, job_submissions_limit=None, return_in_api=False, include_sensitive=False, include_job_connection_info=False, loaded_jobs=None) -> Run` (l.949) — populates `run.service` from `run_model.service_spec` JSON.
- `def switch_run_status(session, run_model, new_status: RunStatus, actor: events.AnyActor = events.SystemActor())` (l.97) — the ONLY sanctioned way to change RunModel.status (emits event).
- `def get_run_spec(run_model) -> RunSpec` (l.154) — parses `run_model.run_spec` JSON.
- `def is_job_ready(probes: Iterable[ProbeModel], probe_specs: Iterable[ProbeSpec]) -> bool` (l.1226).

spec.py: `def validate_run_spec_and_set_defaults(user: UserModel, run_spec: RunSpec, legacy_repo_dir: bool = False)` (l.66): validates run_name against `^[a-z][a-z0-9-]{1,40}$`; sets `repo_id=DEFAULT_VIRTUAL_REPO_ID`/`repo_data=VirtualRunRepoData()` when both None (l.88-91); sets priority default; requires ssh key (l.128-132: `raise ServerClientError("ssh_key_pub must be set if the user has no ssh_public_key")`).

## 2. Repo requirement / virtual repo
`src/dstack/_internal/core/models/repos/virtual.py`: `DEFAULT_VIRTUAL_REPO_ID = "none"` (l.11), `class VirtualRepoInfo(BaseRepoInfo)` with `repo_type: Literal["virtual"]`, `class VirtualRunRepoData(VirtualRepoInfo)`, `class VirtualRepo(Repo)` (programmatic files via `add_file`, tarred by `write_code_file`).

Server mechanism: a run CAN be submitted with `run_spec.repo_id=None, repo_data=None`; `validate_run_spec_and_set_defaults` fills the virtual defaults, then `_get_run_repo_or_error` (runs/__init__.py:1185) sees `repo_data.repo_type == "virtual"` and calls `repos_services.create_or_update_repo(session, project, repo_id, repo_info)` (repos.py:101) which upserts the RepoModel row — i.e. NO prior `/repos/init` call is needed server-side. If `repo_code_hash` is None, no code blob is fetched for the runner (`_get_job_code` in background/pipeline_tasks/jobs_running.py:1745 returns None when `code_hash is None`).

CLI behavior for repo-less configs: `BaseRunConfigurator.apply_configuration` (cli/services/configurators/run.py:112-114) — if `self.get_repo(...)` returns None it calls `init_default_virtual_repo(api)` (cli/services/repos.py:34-37: `repo = VirtualRepo(); api.repos.init(repo)`). The SDK (`RunCollection.get_run_plan`, api/_public/runs.py:498-542) builds `RunSpec(run_name=configuration.name, repo_id=repo.repo_id, repo_data=repo.run_repo_data, repo_code_hash=None-if-no-files, file_archives=..., configuration=..., profile=..., ssh_key_pub=None → server-managed user key)`.

## 3. dstack apply flow for a service
CLI: `ServiceConfigurator` (cli/services/configurators/run.py:716) extends `BaseRunConfigurator.apply_configuration` (l.87) → `self.api.runs.get_run_plan(configuration, repo, configuration_path, profile, ssh_identity_file)` (api/_public/runs.py:470) → HTTP `POST /api/project/{project_name}/runs/get_plan` → router `get_plan` (server/routers/runs.py:112-140; body `GetRunPlanRequest{run_spec: RunSpec, max_offers: Optional[int]}`; deps `ProjectMember()`, `get_client_version`, `use_legacy_repo_dir`) → `runs.get_plan(...)`. Then `self.api.runs.apply_plan(run_plan, repo, reserve_ports)` (api/_public/runs.py:547; uploads code tar via `repos.upload_code` only if `repo.has_code_to_write()`) → `POST /api/project/{project_name}/runs/apply` (routers/runs.py:143-171; body `ApplyRunPlanRequest{plan: ApplyRunPlanInput{run_spec, current_resource}, force: bool}`) → `runs.apply_plan(...)`. Router also calls `users.refresh_ssh_key(session, actor=user)` when user has no ssh key. Other endpoints: `POST /api/runs/list` (root router), `POST /api/project/{p}/runs/get`, `/stop` (`StopRunsRequest{runs_names, abort}`), `/delete`, `/submit` (deprecated, body `SubmitRunRequest{run_spec}`).

## 4. Stop/terminate + status semantics
Terminate programmatically: `runs.stop_runs(session, user, project, runs_names, abort, pipeline_hinter=None)` — this is the idiomatic way (routers use it); it flips status to TERMINATING and RunPipeline (`_process_terminating_item` → `process_terminating_run` in background/pipeline_tasks/runs/terminating.py:61) unregisters the service from the gateway (`_unregister_service`, terminating.py:146) and terminates jobs.

`RunStatus` (core/models/runs.py:652): PENDING, SUBMITTED, PROVISIONING, RUNNING, TERMINATING, TERMINATED, FAILED, DONE; `finished_statuses() = [TERMINATED, FAILED, DONE]`; `is_finished()`. `RunTerminationReason` (l.91): ALL_JOBS_DONE→DONE, JOB_FAILED→FAILED, RETRY_LIMIT_EXCEEDED→FAILED, STOPPED_BY_USER→TERMINATED, ABORTED_BY_USER→TERMINATED, SERVER_ERROR→FAILED (`to_status()`, l.114).

Service semantics (background/pipeline_tasks/runs/active.py `_get_active_run_transition`, l.369): run is RUNNING when ANY replica contributes RUNNING (job RUNNING); PROVISIONING when best is PROVISIONING/PULLING; FAILED (via TERMINATING + JOB_FAILED/RETRY_LIMIT_EXCEEDED) when a replica failed non-retryably; PENDING when all replicas are retrying. `Run.error` = `termination_reason.to_error()`; `Run.status_message` may show "pulling"/"retrying" (runs/__init__.py:1079).

"Ready" for services is stronger than RUNNING: a replica is registered on the gateway/in-server proxy only when its probes are all ready — `_maybe_register_replica` (jobs_running.py:1119-1130) gates on `is_job_ready(job_model.probes, job_spec.probes)`; `is_probe_ready(probe, spec) = probe.success_streak >= spec.ready_after` (services/probes.py:9). If `ServiceConfiguration.model` is set and `probes` omitted, a default `/v1/chat/completions` probe is applied (configurations.py:1019-1026). Service URL: `Run.service: Optional[ServiceSpec]` — for in-server proxy `url = /proxy/services/{project}/{run_name}/`, model at `/proxy/models/{project}/` (services/services/__init__.py:240-282, `_register_service_in_server`); ServiceSpec.model = `ServiceModelSpec(name, base_url, type)`.

## 5. Precedent for server-created runs
`grep submit_run(` over src: only routers/runs.py:217 and internal recursion in apply_plan (runs/__init__.py:608,621). `RunModel(` is instantiated exactly once in prod code (runs/__init__.py:734). So: NO existing code path where the server creates a run without a user API call. Closest precedents (server creates JOBS, not runs): (a) retry — `_build_retry_job_models` (active.py:455); (b) service auto-scaling — `_build_service_scaling_maps` (active.py:576) / `build_scale_up_job_models` (pipeline_tasks/runs/common.py:56); (c) rolling deployment — `_build_rolling_deployment_maps` (active.py:645); (d) scheduled runs — run stays PENDING and RunFetcher picks it up when `next_triggered_at < now` (pipeline_tasks/runs/__init__.py:157-163), then `process_pending_run` (pending.py:43) creates job models. All of these keep the user-created RunModel and attribute job creation to `events.SystemActor()` (see comment at runs/__init__.py:814-817).

## 6. Identity for a background task
- No system/global service user exists. `get_or_create_admin_user(session) -> Tuple[UserModel, bool]` (services/users.py:45; username "admin", GlobalRole.ADMIN, token from `DSTACK_SERVER_ADMIN_TOKEN` or uuid4) is created at startup (app.py:142) and is the only guaranteed user.
- `UserModel.token: Mapped[DecryptedString] = mapped_column(EncryptedString(200), unique=True)` + `token_hash` (models.py:218-220); plaintext via `admin.token.get_plaintext_or_error()` (used in app.py:166,198). ssh_private_key/ssh_public_key columns nullable (pre-0.19.33 users); `create_user` (users.py:160) always generates an RSA pair.
- Acting "as" a project: load `ProjectModel` via `projects.get_project_model_by_name_or_error(session, project_name)` (services/projects.py:589; joinedloads backends+members) and pass it straight to the runs service functions — the service layer does no auth (auth is only `ProjectMember()` in security/permissions.py:112, a FastAPI dep resolving Bearer token → (UserModel, ProjectModel)). Idiomatic choice for an endpoint feature: store the endpoint creator's `user_id` on the endpoint model and submit runs as that user (events/attribution stay correct); events emitted by the background machinery itself use `events.SystemActor()` (services/events.py:34; `AnyActor = Union[SystemActor, UserActor]`, `emit(session, message, actor, targets)` l.171).
- Multi-replica-safe background patterns: (a) Pipeline framework — subclass `Pipeline[ItemT]`/`Fetcher`/`Worker`/`Heartbeater` (background/pipeline_tasks/base.py; items carry lock_token/lock_expires_at; fetch uses `.with_for_update(skip_locked=True, key_share=True)` + `lock_owner` — see RunFetcher.fetch, pipeline_tasks/runs/__init__.py:132-233), register in `PipelineManager.__init__` (pipeline_tasks/__init__.py:35-49), model gets `PipelineModelMixin` columns (models.py:204-207); or (b) apscheduler scheduled task — add in `start_scheduled_tasks()` (background/scheduled_tasks/__init__.py:37). Both started in app.py lifespan iff `settings.SERVER_BACKGROUND_PROCESSING_ENABLED` (app.py:178-183). DB sessions in background code come from `get_session_ctx()` (server/db.py).

## 7. Naming and tagging
- Name rule: `validate_dstack_resource_name` → regex `^[a-z][a-z0-9-]{1,40}$` (core/services/__init__.py:6-12). Auto-generation: `generate_name()` (utils/random_names.py:253, adjective-animal) + `-{idx}` uniqueness loop scoped to project + non-deleted (`_generate_run_name`, runs/__init__.py:1134).
- Uniqueness: enforced among non-deleted runs per project under an advisory lock; submitting with an existing name of a FINISHED run marks the old run deleted (submit_run l.716-718); an ACTIVE same-name run makes apply_plan try in-place update or raise "Cannot override active run".
- Tags/labels: RunModel (models.py:405-465) has NO tag column. `ProfileParams.tags: Optional[Dict[str,str]]` (core/models/profiles.py:462) rides inside run_spec JSON and is propagated to backend cloud resources — not SQL-filterable. To link runs to an owning endpoint: use a deterministic run_name (e.g. derived from endpoint name) and/or an FK from the new EndpointModel to `RunModel.id`; RunModel.fleet_id (models.py:422) is prior art for run→resource attachment.

## Minimal server-side call sequence (verified building blocks)
```python
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.services import projects as projects_services
from dstack._internal.server.services import runs as runs_services
from dstack._internal.server.services import users as users_services
from dstack._internal.core.models.runs import RunSpec, RunStatus
from dstack._internal.core.models.configurations import ServiceConfiguration

async with get_session_ctx() as session:
    project = await projects_services.get_project_model_by_name_or_error(session, project_name)
    user = await users_services.get_user_model_by_name(session, username)  # e.g. endpoint creator or "admin"
    run_spec = RunSpec(
        run_name="my-endpoint-svc",            # or None -> auto-generated
        configuration=ServiceConfiguration(commands=[...], port=8000, model="<name>", env=..., replicas=...),
        # repo_id / repo_data left None -> virtual repo defaults applied server-side
        ssh_key_pub=None,                       # ok iff user.ssh_public_key is set
    )
    run = await runs_services.submit_run(session=session, user=user, project=project,
                                         run_spec=run_spec, pipeline_hinter=None)  # commits

# monitor (poll):
async with get_session_ctx() as session:
    project = await projects_services.get_project_model_by_name_or_error(session, project_name)
    run = await runs_services.get_run_by_name(session=session, project=project, run_name=name)
    # run.status (RunStatus), run.error, run.service.url / run.service.model.base_url
    # readiness: run.status == RunStatus.RUNNING (+ probe-based gateway registration already gated server-side)

# terminate:
async with get_session_ctx() as session:
    await runs_services.stop_runs(session=session, user=user, project=project,
                                  runs_names=[name], abort=False, pipeline_hinter=None)  # commits
```
Testing helpers exist: `create_user`, `create_project`, `create_repo`, `create_run(session, project, repo, user, run_name=None, status=RunStatus.SUBMITTED, run_spec=None, ...) -> RunModel` in src/dstack/_internal/server/testing/common.py (create_run at l.365).

Not verified/does not exist: no `runs/apply.py` module (apply logic lives in runs/__init__.py); no server-side "preset service config" store; no endpoint-like resource today; no system user; no run tag columns.

## Gotchas
1) `submit_run` COMMITS the session multiple times (also via its internal `delete_runs` call) and uses cross-process locking (`pg_advisory_xact_lock` on Postgres / in-memory lockset on SQLite) for run-name uniqueness — call it with a fresh session from `get_session_ctx()` in a background task, never inside another transaction you expect to control.
2) `validate_run_spec_and_set_defaults` (called by both apply_plan and submit_run) raises ServerClientError unless `run_spec.ssh_key_pub` is set OR `user.ssh_public_key` is non-empty (spec.py:128-132). Users created via `create_user` always have keys; users created via testing helpers or pre-0.19.33 may not.
3) `submit_run` does NOT apply plugin policies — only `get_plan`/`apply_plan` call `apply_plugin_policies`. If the endpoint feature should respect plugins, go through `apply_plan(plan=ApplyRunPlanInput(run_spec=...), force=True)` rather than `submit_run` directly. Note `apply_plan` with `run_spec.run_name=None` just delegates to submit_run.
4) For services, `submit_run` synchronously calls `services.register_service` (runs/__init__.py:758-760, marked FIXME) — it can raise ResourceNotExistsError (gateway referenced but missing, or `FORBID_SERVICES_WITHOUT_GATEWAY` set) or ServerClientError (autoscaling/rate_limits without gateway). An endpoint background task must handle these as submission failures.
5) No membership/authorization checks exist in the service layer — `ProjectMember()` in routers is the only gate. A background task passing any UserModel works; the run is attributed to that user (RunModel.user_id, events UserActor).
6) There is NO system user. Only the `admin` user (username "admin", GlobalRole.ADMIN) is guaranteed to exist (created in app.py:142 at startup). If endpoints should be attributed to the submitting user, store the endpoint's creator user_id and pass that UserModel.
7) RunModel has NO tags column. `ProfileParams.tags` (profiles.py:462) exists in run_spec JSON only (propagated to cloud resources, not SQL-queryable). Link endpoint→run via run_name (regex `^[a-z][a-z0-9-]{1,40}$`, unique among non-deleted runs per project) or an FK to RunModel.id on the new endpoint table.
8) Run status is not a reliable "ready" signal for services: RunStatus.RUNNING means ≥1 replica job is RUNNING, but the replica is only registered on the gateway/proxy after all its probes are ready (`is_job_ready`, jobs_running.py:1119-1130; `is_probe_ready` = success_streak >= spec.ready_after). If `model:` is set and probes omitted, a default /v1/chat/completions probe is added. For endpoint health-checking, either rely on probes+RUNNING or poll the service URL directly.
9) Do NOT set RunModel.status directly — use `switch_run_status()` (models.py:437 docstring) so an event is emitted; run termination is done by setting status TERMINATING + termination_reason (+ `skip_min_processing_interval=True`) and letting RunPipeline finish it — `stop_runs` does exactly this.
10) Background processing can be disabled per-replica (`SERVER_BACKGROUND_PROCESSING_ENABLED`, app.py:178); pipelines poll the DB, and the optional `pipeline_hinter` (services/pipelines.py, a FastAPI dependency) only reduces latency — passing None from a background task is fine, or use `get_pipeline_manager().hinter` in-process.
11) `submit_run` deletes any existing finished run with the same run_name (runs/__init__.py:716) — reusing a deterministic endpoint-derived run name will silently erase previous run history.
12) Runs with `schedule` in the profile start as PENDING with 0 replicas (runs/__init__.py:730-732); otherwise initial status SUBMITTED.
