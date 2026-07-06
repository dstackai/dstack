# service-runtime-health

## Summary
Services with `model:` set get an OpenAI-compatible endpoint via a ServiceSpec stored on RunModel; without a gateway, the in-server proxy serves `/proxy/services/<project>/<run>/...` and `/proxy/models/<project>/...` (the latter marked deprecated but functional). Auth is a Bearer token of any project member, but server code never needs HTTP: probes already health-check model endpoints in-process by SSH-tunneling to the replica's service port (`get_service_replica_client(job)` in `job_replica_http_client.py`) and POSTing `{prefix}/chat/completions`. A default chat-completions probe is auto-generated for OpenAI-format models, executed every 3s by the multi-replica-safe `process_probes` scheduled task, and probe success (`success_streak >= ready_after`) gates the `JobModel.registered` flag which is what "replica ready" means. The endpoint health-checker should reuse the exact probe mechanism (job-level SSH tunnel + httpx over UDS), which works identically for gateway and non-gateway services.

## Key files
- src/dstack/_internal/server/background/scheduled_tasks/probes.py — process_probes, _process_probe_async, _execute_probe — THE reference implementation for health-checking a deployed model: batch-locks due ProbeModels (multi-replica safe), tunnels to the replica, POSTs the probe request, updates success_streak. `_execute_probe` (lines 106-126) is exactly what the endpoint health-checker should copy.
- src/dstack/_internal/server/services/jobs/job_replica_http_client.py — get_service_replica_client(job: JobModel) -> AsyncGenerator[httpx.AsyncClient, None] — Async context manager giving an httpx client to a job's service port over an SSH tunnel + Unix socket. No HTTP auth, no gateway needed. Lines 21-27.
- src/dstack/_internal/server/services/jobs/job_replica_tunnel.py — get_service_replica_tunnel, SSH_CONNECT_TIMEOUT — Builds the tunnel via container_ssh_tunnel(job, forwarded_sockets=[SocketPair(remote=IPSocket('localhost', job_spec.service_port), local=UnixSocket(...))]).
- src/dstack/_internal/server/services/jobs/configurators/base.py — _probes (line 410), _probe_config_to_spec (458), _openai_model_probe_spec (472) — Default probe generation: if ServiceConfiguration.probes is None and model is OpenAIChatModel, generates POST {prefix}/chat/completions probe with body {model, messages:[{role:user,content:'hi'}], max_tokens:1}, timeout 30s.
- src/dstack/_internal/server/services/services/__init__.py — register_service (49), _register_service_in_gateway (99), _register_service_in_server (240), _get_service_spec (320) — Where `model:` becomes URLs. In-server: service_url=/proxy/services/{project}/{run}/ (273), model_url=service_url+prefix for openai / /proxy/models/{project}/ for tgi (274-277). Gateway: https://{run_name}.{wildcard_domain}, model at gateway.{wildcard_domain} (160-172). Result stored as run_model.service_spec JSON (96).
- src/dstack/_internal/server/services/proxy/repo.py — ServerProxyRepo.get_service (47), list_models (143), get_model (172) — In-server proxy data source. get_service only returns runs with gateway_id IS NULL, JobStatus.RUNNING, registered==True, job_num==0. list_models requires RunStatus.RUNNING + service_spec.options['openai']['model'].
- src/dstack/_internal/proxy/lib/services/service_connection.py — ServiceConnectionPool, ServiceConnection, get_service_replica_client(service, repo, service_conn_pool) (140) — Proxy-lib variant of replica client (pooled, persistent tunnels). Used by the in-server proxy and model proxy routers.
- src/dstack/_internal/proxy/lib/services/model_proxy/clients/openai.py — OpenAIChatCompletions.generate/stream — Existing typed client that POSTs {prefix}/chat/completions given an httpx.AsyncClient — reusable for a higher-level health check with response validation.
- src/dstack/_internal/proxy/lib/routers/model_proxy.py — get_models, post_chat_completions — OpenAI-compatible HTTP API: GET /proxy/models/{project}/models, POST /proxy/models/{project}/chat/completions. Mounted in app.py:261 with deprecated=True (still functional).
- src/dstack/_internal/server/services/probes.py — probe_model_to_probe, is_probe_ready — is_probe_ready(probe, spec) = probe.success_streak >= spec.ready_after.
- src/dstack/_internal/server/services/runs/__init__.py — is_job_ready (1226), submit_run (register_service call at 760), run_model_to_run (service_spec at 979-1004) — is_job_ready = all probes ready; Run.service: Optional[ServiceSpec] populated from RunModel.service_spec.
- src/dstack/_internal/server/background/pipeline_tasks/jobs_running.py — _initialize_running_job_probes (1101), _maybe_register_replica (1119), _register_service_replica (1162) — Probes created when job reaches RUNNING; JobModel.registered set True only when all probes ready (and gateway registration succeeds if gateway-based).
- src/dstack/_internal/core/models/configurations.py — ProbeConfig (365), ServiceConfiguration.model (993), .probes (1019), convert_model validator (1058), probe constants (61-71) — model: str is coerced to OpenAIChatModel(format='openai'); OPENAI_MODEL_PROBE_TIMEOUT=30, DEFAULT_PROBE_INTERVAL=15, DEFAULT_PROBE_READY_AFTER=1.
- src/dstack/_internal/core/models/runs.py — ProbeSpec (245), JobSpec.probes/service_port (299-301), Probe (390), JobSubmission.probes (428), ServiceModelSpec (635), ServiceSpec (643), RunStatus (652) — ProbeSpec is the resolved probe stored in JobSpec; Probe(success_streak) surfaces per-submission probe state to clients.
- src/dstack/_internal/proxy/lib/deps.py — ProxyAuth, ProxyAuthContext — Bearer-token auth for proxy routes; enforced iff service.auth (service proxy) and always for model proxy.
- src/dstack/_internal/proxy/lib/schemas/model_proxy.py — ChatCompletionsRequest, ChatCompletionsResponse, ChatCompletionsChunk, ModelsResponse — Typed OpenAI-compatible request/response schemas already in the codebase.

## Details
## 1. The `model:` property on services

`ServiceConfiguration.model: Optional[AnyModel]` — `src/dstack/_internal/core/models/configurations.py:993-1003`. A plain string is coerced by the `convert_model` validator (configurations.py:1058-1062):

```python
@validator("model", pre=True)
def convert_model(cls, v: Optional[Union[AnyModel, str]]) -> Optional[AnyModel]:
    if isinstance(v, str):
        return OpenAIChatModel(type="chat", name=v, format="openai")
    return v
```

Model types (`src/dstack/_internal/core/models/services.py`): `BaseChatModel` (13), `TGIChatModel` (21), `OpenAIChatModel` (58, `prefix` default `"/v1"` at line 72), `ChatModel = Annotated[Union[TGIChatModel, OpenAIChatModel], Field(discriminator="format")]` (75), `AnyModel = Union[ChatModel]` (76).

**Registration flow**: `submit_run` calls `await services.register_service(session, run_model, run_spec)` at `src/dstack/_internal/server/services/runs/__init__.py:760` (comment: "FIXME: Register services asynchronously in the background"). `register_service` (`src/dstack/_internal/server/services/services/__init__.py:49-96`) resolves the gateway (explicit ref / default / `gateway: false`) and either:
- `_register_service_in_gateway` (line 99): registers on every gateway connection via `client.register_service(...)` (`src/dstack/_internal/server/services/gateways/client.py:37-74`; when `"openai" in options` it also calls `register_openai_entrypoint` for `gateway.<domain>`, lines 52-54).
- `_register_service_in_server` (line 240): no gateway. Rejects SGLang router, non-auto https, autoscaling (min!=max), rate_limits. Then builds URLs (lines 273-277):

```python
service_url = f"/proxy/services/{run_model.project.name}/{run_model.run_name}/"
if isinstance(run_spec.configuration.model, OpenAIChatModel):
    model_url = service_url.rstrip("/") + run_spec.configuration.model.prefix
else:
    model_url = f"/proxy/models/{run_model.project.name}/"
```

`_get_service_spec` (line 320-331) produces `ServiceSpec(url=service_url)` with `model=ServiceModelSpec(name, base_url=model_url, type)` and `options=get_service_options(configuration)`. `get_service_options` (`src/dstack/_internal/server/services/services/options.py:48-53`) sets `options["openai"] = {"model": conf.model.dict()}` after `complete_service_model` (options.py:10-23) fills TGI `chat_template`/`eos_token` from HuggingFace (network call, may raise `ServerClientError`). Result stored as `run_model.service_spec = service_spec.json()` (services/__init__.py:96). Gateway registration failure raises (`GatewayError` / `ServerClientError`) synchronously from submit.

`ServiceModelSpec` / `ServiceSpec` — `src/dstack/_internal/core/models/runs.py:635-649`; `Run.service: Optional[ServiceSpec]` (runs.py:693) is populated in `run_model_to_run` (`server/services/runs/__init__.py:979-1004`).

**In-server model listing**: `ServerProxyRepo.list_models` (`src/dstack/_internal/server/services/proxy/repo.py:143-170`) — runs where `gateway_id IS NULL`, `service_spec IS NOT NULL`, `RunStatus.RUNNING`, and `service_spec.options["openai"]["model"]` present. `get_model` (172-178) picks the newest by `created_at` on name collision.

## 2. URL formats

**Without a gateway (in-server proxy, always available unless `settings.FORBID_SERVICES_WITHOUT_GATEWAY`, services/__init__.py:89-95):**
- Service: `/proxy/services/{project_name}/{run_name}/{path}` — router `src/dstack/_internal/server/services/proxy/routers/service_proxy.py:31-49`, mounted at `src/dstack/_internal/server/app.py:260`.
- Model (OpenAI-compatible): `GET /proxy/models/{project_name}/models` and `POST /proxy/models/{project_name}/chat/completions` — router `src/dstack/_internal/proxy/lib/routers/model_proxy.py:26-65`, mounted at app.py:261 **with `deprecated=True`** (still functional; for `format: openai` models the ServiceSpec now points clients at `/proxy/services/<project>/<run><prefix>` instead, i.e. straight through the service proxy — the model proxy is mainly needed for TGI-format translation).
- These are paths relative to the dstack server's base URL; auth via Bearer token (see below).

**With a gateway** (services/__init__.py:160-177): service at `{http|https}://{run_name}.{wildcard_domain}`; model endpoint at `{http|https}://gateway.{wildcard_domain}` (or `service_url + model.prefix` for openai format). Requires wildcard domain DNS; served by Nginx on the gateway instance.

## 3. Auth for calling through the proxy

- Both proxy routers use `ProxyAuth` (`src/dstack/_internal/proxy/lib/deps.py:87-106`): `HTTPBearer` credentials → `ProxyAuthContext.enforce()` (deps.py:71-84) → `BaseProxyAuthProvider.is_project_member(project_name, token)`. Server implementation: `ServerProxyAuthProvider` (`src/dstack/_internal/server/services/proxy/auth.py:7-12`) → `is_project_member(session, project_name, token)` (`src/dstack/_internal/server/security/permissions.py:278-283`). So the token is **any project member's user token** (the same `Authorization: Bearer <dstack user token>` used for the REST API).
- Model proxy always enforces (`APIRouter(dependencies=[Depends(ProxyAuth(auto_enforce=True))])`, model_proxy.py:23). Service proxy enforces only when `service.auth` is true (`server/services/proxy/services/service_proxy.py:39-40`; `ServiceConfiguration.auth` default `True`, configurations.py:1012).
- **In-process alternative: yes.** Server code does not need HTTP+token at all — see mechanism below. There is no in-process function that "calls the FastAPI route"; instead server code opens the same SSH tunnel the proxy uses.

## 4. Service probes

- Config: `ProbeConfig` (`configurations.py:365-459`): `type: Literal["http"]`, `url` (default `/`), `method` (default `get`), `headers`, `body`, `timeout` (default 10s, min 1s), `interval` (default 15s), `ready_after` (default 1), `until_ready` (default False). `ServiceConfiguration.probes: Optional[list[ProbeConfig]]` (configurations.py:1019-1026) — `None` means "default"; docstring: "If `model` is set, defaults to a `/v1/chat/completions` probe."
- Default generation: job configurator `_probes()` (`server/services/jobs/configurators/base.py:410-419`) — explicit probes are converted by `_probe_config_to_spec` (458); otherwise, if `isinstance(model, OpenAIChatModel)`, returns `[_openai_model_probe_spec(model.name, model.prefix)]` (472-491): `POST {prefix}/chat/completions`, JSON body `{"model": <name>, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}`, `Content-Type: application/json`, `timeout=OPENAI_MODEL_PROBE_TIMEOUT` (30s, configurations.py:71), `interval=15`, `ready_after=1`. Note: **TGI-format models get no default probe.** Resolved probes live in `JobSpec.probes: list[ProbeSpec]` (`core/models/runs.py:301`, spec class at 245-255).
- DB: `ProbeModel` (`server/models.py:1117-1133`): `id, name, job_id, probe_num, due, success_streak, active`; unique `(job_id, probe_num)`.
- Lifecycle: created when the job first reaches RUNNING — `_initialize_running_job_probes` (`server/background/pipeline_tasks/jobs_running.py:1101-1116`). Evaluated by scheduled task `process_probes` (`server/background/scheduled_tasks/probes.py:29-79`) registered at `IntervalTrigger(seconds=3, jitter=1)` (`server/background/scheduled_tasks/__init__.py:47`). Multi-replica-safe pattern: `get_locker(get_db().dialect_name).get_lockset(ProbeModel.__tablename__)` + `select(...).where(due <= now, active == True).limit(100).with_for_update(skip_locked=True, key_share=True)`; actual HTTP executed off-session via an `AsyncIOScheduler` job (`_process_probe_async`, 82-103) which then updates `success_streak` (reset to 0 on failure, +1 on success) and `due = now + interval`.
- Execution (`_execute_probe`, probes.py:106-126):

```python
async with get_service_replica_client(probe.job) as client:
    resp = await client.request(
        method=probe_spec.method,
        url="http://dstack" + probe_spec.url,   # host is dummy; transport is a UDS
        headers=[(h.name, h.value) for h in probe_spec.headers],
        content=probe_spec.body,
        timeout=probe_spec.timeout,
        follow_redirects=False,
    )
    return resp.is_success
```

- Status reflection: `Probe(success_streak=int)` (`core/models/runs.py:390-391`) in `JobSubmission.probes` (runs.py:428) via `probe_model_to_probe` (`server/services/probes.py:5-6`). Readiness: `is_probe_ready(probe, spec) = probe.success_streak >= spec.ready_after` (`server/services/probes.py:9-10`); `is_job_ready(probes, probe_specs)` = all ready (`server/services/runs/__init__.py:1226-1227`). Probe failures do NOT fail/terminate the job; they only delay/gate readiness. Probes deactivate when the job leaves RUNNING or when `until_ready` and threshold reached (probes.py:63-69).

## 5. Service readiness today

- Job statuses: SUBMITTED → PROVISIONING → PULLING → RUNNING → ... (`core/models/runs.py:62-78`); run statuses PENDING/SUBMITTED/PROVISIONING/RUNNING/TERMINATING/... (runs.py:652-667).
- Run status aggregation: `_analyze_active_run` + `_get_active_run_transition` (`server/background/pipeline_tasks/runs/active.py:182-236, 369-409`): the run is RUNNING as soon as **any** replica job is RUNNING (active.py:393-394). So `RunStatus.RUNNING` alone does NOT mean the model answers requests.
- The real readiness signal is `JobModel.registered` (`server/models.py:578`, "whether the replica is registered to receive service requests"): `_maybe_register_replica` (`jobs_running.py:1119-1159`) sets `registered=True` only for services when `job_num == 0`, probes exist and `is_job_ready(...)` is True; for gateway services it first registers the replica on the gateway (`_register_service_replica`, 1162+; in-server case returns None and just flips the flag). The in-server proxy only routes to `registered == True` jobs (`ServerProxyRepo.get_service`, repo.py:57).
- Rolling deployment: driven by `deployment_num` comparison (`_has_out_of_date_replicas`, active.py:627-642) with surge/teardown in `_build_rolling_deployment_maps` (active.py:645-701); new replicas must become `registered` (probe-ready) before old ones are torn down. `ready_after`/`until_ready` on probes exist specifically for this.

## 6. Concrete mechanism for the endpoint health-checker

**Recommended (verified, no new plumbing): replicate `_execute_probe`.** Given the deployed service's RunModel, pick a `JobModel` with `status == JobStatus.RUNNING` (and `job_num == 0`), then:

```python
from dstack._internal.server.services.jobs.job_replica_http_client import get_service_replica_client
import orjson

body = orjson.dumps({
    "model": model_name,
    "messages": [{"role": "user", "content": "hi"}],
    "max_tokens": 1,
}).decode()
async with get_service_replica_client(job_model) as client:  # SSH tunnel + httpx over UDS
    resp = await client.request(
        method="post",
        url="http://dstack/v1/chat/completions",  # or prefix.rstrip('/') + '/chat/completions'
        headers=[("Content-Type", "application/json")],
        content=body,
        timeout=30,
    )
    ok = resp.is_success
```

This is exactly what probes do today (probes.py:106-126) and works identically for gateway and non-gateway services because it tunnels straight to the replica (bypasses gateway/proxy/auth). Requires the job to have `job_spec.service_port` set (true for all services since 0.19.19; `get_service_port` fallback at `core/models/runs.py:757-762`). `get_service_replica_client(job)` signature: `server/services/jobs/job_replica_http_client.py:22-27`; underlying tunnel `get_service_replica_tunnel` uses `container_ssh_tunnel(job, forwarded_sockets=..., options=...)` (`server/services/ssh.py:81-98`), `SSH_CONNECT_TIMEOUT = timedelta(seconds=10)` (`job_replica_tunnel.py:20`).

**Even simpler for the endpoint feature**: don't run your own HTTP check at all — rely on the existing probe machinery. If the authored service config has `model:` set (OpenAI format) and `probes` unset, dstack auto-creates the chat-completions probe; the endpoint processor can then just poll `JobModel.registered` (or `is_job_ready(job_model.probes, job_spec.probes)` via `server/services/runs/__init__.py:1226`) to decide active/failed. `run.status == RunStatus.RUNNING` + `job.registered == True` == "model verified to answer /v1/chat/completions".

**Higher-level typed alternative** (validates the OpenAI response shape): use the proxy-lib stack in-process — `ServerProxyRepo(session).get_model(project, model_name)` + `.get_service(project, run_name)` (`server/services/proxy/repo.py:47,172`), `get_service_replica_client(service, repo, service_conn_pool)` (`proxy/lib/services/service_connection.py:140-163`, pool from `app.state.proxy_dependency_injector` — `ServerProxyDependencyInjector` set in app.py:106, defined in `server/services/proxy/deps.py:11`), then `get_chat_client(model, http_client).generate(ChatCompletionsRequest(model=..., messages=[...], max_tokens=1))` (`proxy/lib/services/model_proxy/model_proxy.py:11`, `clients/openai.py:21-33`, request schema `proxy/lib/schemas/model_proxy.py:11-27`). Caveat: `ServerProxyRepo.get_service` only returns non-gateway, `registered` services — so this path can't health-check gateway-based or not-yet-registered replicas.

**HTTP path (not recommended for server-internal use)**: `POST {server}/proxy/models/{project}/chat/completions` with `Authorization: Bearer <user token>` — requires a valid project-member token and is marked deprecated in app.py:261.

## Gotchas
1. Run `RunStatus.RUNNING` fires when ANY replica job is RUNNING (runs/active.py:393-394) — it is NOT "model ready". The readiness signal is `JobModel.registered` (set only after all probes pass, jobs_running.py:1119-1130). An endpoint health-checker that only watches run status would mark endpoints active before the model can serve.
2. `/proxy/models/...` router is mounted with `deprecated=True` (app.py:261) — still works, but new code/URLs should prefer the service-proxy path `/proxy/services/<project>/<run><prefix>/chat/completions` for openai-format models, which is what `_register_service_in_server` now advertises (services/__init__.py:275).
3. The default chat-completions probe is generated ONLY when `model` is `OpenAIChatModel` and `probes` is None (`_probes()`, configurators/base.py:410-419). A bare string `model: <name>` coerces to OpenAIChatModel, so the common case is covered; TGI-format models get NO default probe.
4. Probes never fail the job — a permanently unhealthy service stays RUNNING with `registered=False` forever. An endpoint feature that wants a "failed" terminal state must add its own timeout on top.
5. `get_service_replica_client` exists TWICE with different signatures: `server/services/jobs/job_replica_http_client.py:22` takes a `JobModel` (context manager, fresh tunnel per call — use this from background tasks) vs `proxy/lib/services/service_connection.py:140` takes `(Service, BaseProxyRepo, ServiceConnectionPool)` (pooled, used by proxy routers). Don't confuse them in the plan.
6. `ServerProxyRepo.get_service`/`list_models` exclude gateway-based runs (`RunModel.gateway_id.is_(None)`) and unregistered jobs — the in-server proxy cannot reach gateway services. The job-tunnel mechanism (probes path) works for both.
7. In probe execution the URL host is literally `"http://dstack"` — a placeholder; transport is a Unix socket. Don't "fix" it.
8. Gateway registration happens synchronously inside `submit_run` (runs/__init__.py:758-760, marked FIXME) and can raise; `complete_service_model` for TGI does a blocking HTTP call to huggingface.co (options.py:25-45).
9. Multi-replica-safe background pattern to copy: `process_probes` (scheduled_tasks/probes.py:29-79) uses `get_locker(get_db().dialect_name).get_lockset(...)` + `with_for_update(skip_locked=True, key_share=True)` + due-based scheduling; scheduled via `AsyncIOScheduler` in `background/scheduled_tasks/__init__.py` (there is also `background/pipeline_tasks/` for the pipeline-style processors).
10. Auth token for HTTP proxy calls is a plain dstack user token of any project member (permissions.py:278-283); there is no separate service/model API key concept.
