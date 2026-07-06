# Implementation plan: `endpoint` configuration type

Status: **implementation in progress**. This document started as a research-backed implementation plan verified against `master` @ `28ea5f86f` (2026-07-03); it is now also used as the implementation tracker. Line numbers drift; symbol names are the anchor.

## Project thesis

The endpoint feature is not primarily a new CRUD resource. It is a **learning deployment loop**:

1. A user asks dstack to serve a model.
2. If dstack already has a tested preset for that model, it should submit a normal dstack service from that preset and mark the endpoint running when the service is ready.
3. If dstack does not know a working deployment yet, a real agent investigates, uses dstack like a power user, deploys and verifies a final service, and saves what worked as a preset.
4. The next compatible endpoint for that model should be able to use the preset path without paying the agent again.

The preset path and the agent path must converge. If the agent can make a model work once but saves a preset that is too narrow, unreproducible, missing evidence, or unusable without the agent, the feature has not solved the real problem.

Non-negotiable project invariants:

- A preset is a verified deployment artifact, not just a service YAML.
- `resources` are scheduling requirements used for reuse/offer matching; `tested_resources` are exact verified hardware evidence.
- The server owns endpoint state, locking, run linking, stopping/cleanup, and preset persistence. The agent owns deployment investigation and final functional verification.
- The server must not mark an agent-created endpoint running based only on its own service-readiness bookkeeping; the agent must report that the requested model was actually served and answered a real model request.
- Work should be driven by real deployment failures. Avoid adding abstractions before live runs show they are needed.

## 0. Implementation checklist and plan deltas

Keep this section current while implementing. It is the short operational view of the longer plan below: what is already in the working tree, what is still missing for v1, and where the implementation intentionally diverged from the original plan after code/UX review.

### Done

- [x] Research artifacts copied into the repo under `endpoint-implementation-research/`.
- [x] Endpoint core/API/CLI skeleton: `type: endpoint`, `EndpointConfiguration`, endpoint REST schemas/router/client group, `dstack endpoint list|get|logs|stop|preset`, and `dstack apply` support.
- [x] Endpoint DB/pipeline skeleton: `EndpointModel`, migration, pipeline registration, durable locking, fetch/worker flow, events, and status transitions.
- [x] Apply-plan UX aligned with run apply: one stable property table, preset policy, selected preset/offers when present, no `Model`/`Action`/`Service`/`Agent`/custom provisioning section.
- [x] Endpoint plan displays the configured/default `preset_policy` (`reuse-or-create` by default), not the effective fallback path.
- [x] Preset-backed provisioning path: local presets are matched through normal run planning, service runs are submitted through the existing run apply path, and `creation_policy` is not forced to `reuse`.
- [x] Preset planning distinguishes a model-matched preset from a provisionable preset. Preset submission requires available offers for every planned job; `reuse-or-create` can fall through to the agent path when only non-provisionable presets match.
- [x] Endpoint lifecycle safety: conflict-checked submission, server-side stop that stops the linked backing run, and failed-endpoint teardown of the linked non-terminal run.
- [x] Endpoint apply treats any terminal same-name endpoint as finished: no stop prompt; create resets the same endpoint row back to `submitted`, and only non-terminal same-name endpoints require stop/override.
- [x] Preset-backed endpoint submission handles its deterministic service-run-name conflicts like run apply: non-terminal conflicting runs fail before submission, while terminal conflicting runs are left to the existing run submission path to recycle.
- [x] Endpoint readiness uses backing service readiness only: run is `RUNNING`, has a registered running job, and exposes `ServiceSpec.model.base_url`; no extra endpoint probe in v1.
- [x] Preset storage/parsing: `EndpointPresetService`, local-dir implementation, `endpoint-preset` YAML wrapper, ordered `replica_spec_groups`, validation, atomic no-overwrite save, env value redaction, and literal non-secret env preservation.
- [x] Learned preset plumbing: build a preset from a ready service run, record replica spec groups in service order, preserve the number of currently registered running replicas per group, and save it when an agent-provisioned endpoint becomes running.
- [x] Endpoint preset CLI: `dstack endpoint preset list|get --json|delete`. The compact list shows scheduling resources used for reuse/offer matching; exact verified hardware stays in `tested_resources` and is exposed by `get --json`, not the compact list.
- [x] Endpoint status names adjusted: `clauding` while the server agent investigates/deploys, `running` for a ready endpoint, `stopping`/`stopped` for endpoint stop. The runtime `active` alias was removed; local prototype DB rows should be cleaned directly.
- [x] Endpoint UX split from run UX: `dstack endpoint logs` reads endpoint progress logs, `dstack endpoint stop` stops endpoints, top-level `dstack logs`/`dstack stop` remain run-only, and top-level `dstack preset` was removed.
- [x] Running endpoint apply output renders known relative proxy URLs as absolute URLs using the configured API server URL.
- [x] Endpoint migration is safe for Postgres partial indexes and boolean server defaults.
- [x] Agent lifecycle skeleton: `AgentService` abstraction, disabled default, agent settings, `EndpointPlan.provisioning_plan=type:"agent"` when an enabled agent is injected, fake-agent pipeline integration, and a v0 Claude Code subprocess runtime.
- [x] Agent unavailable UX distinguishes a genuinely missing `DSTACK_AGENT_ANTHROPIC_API_KEY` from a configured key with no real agent implementation registered yet.
- [x] Endpoint run identity uses `EndpointModel.service_run_id` for the current/latest service run and `EndpointRunSubmissionModel` for ordered endpoint-submitted run history.
- [x] Structured final-report validation for the endpoint pipeline contract.
- [x] Endpoint-scoped workspace/process handling added as part of the v0 Claude Code runtime, not as standalone scaffolding.
- [x] Raw Anthropic Messages-loop prototype was removed. It was the wrong abstraction; the endpoint agent must use a real agent runtime, not a hand-rolled tool loop.
- [x] Packaged endpoint-agent prompt/context resources: `resources/system_prompt.md` plus repo-root `skills/dstack` and `skills/dstack-prototyping`, force-included into wheels/sdists and copied into each Claude workspace.
- [x] First full learning-loop proof: Claude-created Qwen preset was reused later by `preset_policy: reuse` without invoking Claude; the endpoint reached `running`, answered a model request, and stopped cleanly.
- [x] Focused endpoint tests and static checks currently pass (`pytest` endpoint suites, `ruff`, `pyright`).

### Still open for v1

- [ ] Harden the real Claude Code subprocess runtime based on live failures: restart/resume semantics, stop-time cancellation, duplicate-process prevention, packaging, and live-run efficiency.
- [ ] Finish runtime durability: persisted usage accounting, restart-safe handoff from agent report to linked service run, endpoint stop abort handling, and cleanup of non-final candidate runs.
- [ ] Guard learned-preset quality: scheduling `resources` must stay broad enough for reuse, exact hardware must remain in `tested_resources`, and saved presets must be usable without the agent.
- [ ] Wire structured agent handoff into preset provenance: final candidate run name/id, final service YAML/content, recipe sources, verification summary, and failure summary.
- [ ] Runtime recipe grounding against vLLM recipes / SGLang docs / HF model cards, with mocked zero-network tests.
- [ ] Foreground endpoint apply following server-side endpoint logs/status without attach.
- [ ] Endpoint preset inspect polish: keep `dstack endpoint preset get --json` useful enough for exact `tested_resources`, provenance comments/metadata, and service recipe review without cluttering the compact list output.
- [ ] Real agent runtime dependencies installed automatically by normal server install/deploy paths: local `uv` server installs and server Docker images must include the runtime; no manual post-install dependency step.
- [ ] Endpoint update/version design before in-place updates: a `configuration_version`/deployment guard so stale background workers in multi-server Postgres setups cannot mark a newer endpoint config running.
- [ ] Documentation: endpoint reference schema page, env vars, concepts page, manual e2e runbook, example presets.
- [ ] Real no-preset agent e2e with a small model and budget-confirmed hardware.

### Critical assessment

The endpoint storage/status/preset/run-link side is becoming reasonable. The feature is still not trustworthy because the agent loop and learned-preset quality are not yet proven across repeated real deployments.

Highest current risks:

- Agent works once but saves a preset that is too exact, stale, missing provenance, or not reusable.
- Agent wastes budget because hardware selection, offer inspection, or failure recovery is weak.
- Agent logs/traces are either too noisy for users or too thin for debugging.
- Server restart/stop during `clauding` can leave ambiguous state or orphan candidate runs.
- Duplicate learned presets accumulate without a repair/update policy.
- We overfit code around the first Qwen smoke runs before testing enough real model/backends/failure modes.

### Immediate next steps: repeat the loop, then harden

Do these in order. Do not add more harness surface area until the previous step has produced evidence.

1. **Audit the reused preset after the run.** Confirm the preset's `resources` are scheduling requirements, `tested_resources` are exact evidence, the service recipe is sufficient, and offer matching is not over-narrow. If reuse fails later, fix the preset contract/builder before touching the agent prompt.
2. **Run one fresh no-preset agent deployment with a small model and a confirmed budget.** Capture command count, elapsed time, spend, hardware choice, service YAML, dstack plan output, candidate cleanup, progress logs, final report, and saved preset.
3. **Harden only from observed failures.** Fix concrete problems in prompt/context, endpoint logs, final report validation, preset saving, run linking, or cleanup. Avoid speculative tools/functions.
4. **Add durable agent budget accounting before retries/resumes.** `max_agent_budget` must cap total spend per endpoint provisioning attempt, not just a single subprocess invocation.
5. **Harden restart/stop while clauding.** Stop should abort the live process and stop linked/candidate runs using explicit submission records. Restart should reconcile existing workspace, final report, and submissions before launching anything new.
6. **Move to a more common/interesting model only after the small loop repeats.** Confirm hardware and budget before trying larger models. Use those runs to evolve hardware-selection behavior and recipe grounding.

### How to overcome the current risks

Treat this as a working hypothesis, not a fixed design. After each real endpoint run, update the plan with what actually happened and remove or change tactics that did not help.

| issue | realistic mitigation | evidence to collect | reconsider if |
|---|---|---|---|
| Learned preset works once but is not reusable | Run an immediate preset-reuse test after every successful agent deployment. Validate that the saved `service` + `resources` can be planned/submitted without the agent and that `tested_resources` are only evidence. | apply plan path selected, offers shown, final service run, endpoint status, model request result, saved preset YAML before/after | the preset path fails for reasons unrelated to transient capacity; then fix preset contract/builder before prompt changes |
| Preset `resources` are too exact or too loose | Keep `resources` sourced from the final service config, but add validation/reporting that flags exact GPU names or full exact CPU/memory/disk constraints in learned presets unless explicitly justified by the service shape. Do not auto-generalize blindly; first inspect the agent's service YAML and the run plan. | final service YAML, saved `resources`, saved `tested_resources`, offer count before/after, reason for any exact GPU/model constraint | exact constraints repeatedly block reuse, or broad constraints repeatedly schedule hardware that cannot serve the model |
| Agent chooses poor hardware or wastes attempts | Give the agent a required decision trace: model sizing evidence, candidate hardware envelope, current dstack offers, planned service resources, and why it is submitting now. Start with prompt/context; only add server-side enforcement after observed bad behavior is clear. | recipe/model sources, offer table excerpt, chosen resources, rejected alternatives, command count, elapsed time, GPU spend | the trace is absent or useless in two real runs; then enforce a structured pre-submit decision artifact before `dstack apply -y -d` |
| Agent logs are noisy or unhelpful | Split logs into two layers: endpoint log gets concise major events authored by the agent; workspace trace stores command output, YAML, raw logs, and final report. Do not put full CLI output or service logs in endpoint logs. | `dstack endpoint logs <endpoint>` readability, workspace artifacts, ability to diagnose failure without server stdout | endpoint logs still duplicate/replay, hide important state, or force reading server logs for normal debugging |
| Restart during `clauding` duplicates work or loses the final run | Reconcile before launch: check existing process metadata, final report, endpoint run submissions, linked `service_run_id`, and live candidate runs. Do not start a new agent until reconciliation decides the previous attempt is unrecoverable. | restart test with a live process, restart test after final report before link, endpoint submissions, linked run, no duplicate paid process | reconciliation logic becomes fragile or still misses cases; then consider moving agent execution to a separately tracked durable task model |
| Stop during `clauding` leaks resources | Add process cancellation and candidate-run cleanup using `EndpointRunSubmissionModel`, not name heuristics. Endpoint stop should request abort, stop linked/submitted non-terminal runs, then finish through the normal run lifecycle. | stop during Claude process, stop after candidate run submitted, final run statuses, endpoint stopped, no running GPU run | cancellation depends on runtime behavior we cannot rely on; then isolate agent execution in a managed process/task with explicit supervisor state |
| Budget cap can be bypassed by restart/resume | Persist provider usage/spend per endpoint provisioning attempt and check remaining budget before starting another agent process. Until this exists, do not add automatic retries/resumes that can spend again. | Claude reported usage/cost, persisted attempt spend, remaining budget, refusal path when exhausted | Claude Code cannot expose reliable usage data; then use a stricter wall-clock/process cap plus operator-visible warning until runtime changes |
| Duplicate learned presets accumulate | Keep append-only for v1, but add inspection/deletion and a simple duplicate report. Do not auto-update until the harness can prove an older preset is not reproducible under its claimed conditions. | duplicate model/resource list, preset source endpoint/run, reuse success/failure per preset | duplicates make selection unstable; then add deterministic ranking or explicit user-selected preset before adding automatic update |
| Agent harness design overfits early Qwen runs | Maintain a scenario ladder: one tiny public model, one slightly larger common model, one gated/HF-token model, one no-offers/constraint case, one failure-cleanup case. Change harness only after comparing patterns across at least two scenarios unless the bug is clearly blocking. | per-scenario run notes, failure categories, command counts, spend, preset reuse result | the first two scenarios expose contradictory needs; then pause and rework the harness contract rather than patching locally |

Near-term implementation strategy:

1. Prefer prompt/context and artifact requirements for the first two real runs. They are cheaper to change and reveal what the agent naturally does.
2. Add server-side validation only where the failure would be expensive or dangerous: wrong project/user run, missing service `model`, missing final verification, budget exhaustion, leaked non-terminal runs, invalid preset shape.
3. Keep every hardening change tied to a reproducible trace: command transcript, endpoint log, final report, saved preset, and dstack run state.
4. After each real run, classify the issue as one of: dstack/backend provisioning bug, agent decision bug, prompt/context gap, preset contract bug, lifecycle/recovery bug, or UX/logging bug. Fix the right layer; do not let agent failures hide dstack/backend failures.
5. Be willing to change runtime approach if Claude Code cannot reliably run non-interactively, expose usage, cancel, preserve artifacts, or package cleanly in server installs/Docker.

### Adjusted from the original plan

- Preset service responsibility was narrowed to **storage only**. Matching, planning, and service apply live outside `EndpointPresetService`.
- Presets now store `replica_spec_groups` as ordered groups of `ResourcesSpec`, separate from the service config. Group order must match `ServiceConfiguration.replica_groups`; the implicit no-replica-groups case uses group `"0"`.
- Presets do **not** store backend, region, or instance type in v1. They store the tested resource topology that can be replanned against current fleets.
- A learned preset records how many registered running replicas existed per replica group at save time. Autoscaling metrics, scaling validation, and benchmark metadata are Later.
- Preset matching does **not** force `creation_policy: reuse`; default `reuse-or-create` may use elastic fleets that can provision new instances.
- Endpoint plan `preset_policy` remains the configured/default policy; the selected path (`preset`, `agent`, or `none`) is represented only by `provisioning_plan`.
- Endpoint config changes are handled like current run UX: prompt to stop/override, with the backing service cleanup performed server-side. In-place update/rolling redeploy is Later.
- Later endpoint config updates must reuse the existing service-run `get_plan`/`apply_plan`/rolling deployment machinery, and endpoint DB updates must be guarded by a configuration/deployment version for multi-server safety.
- Stop/override applies only to non-terminal existing endpoints. Terminal endpoints are replaceable like finished runs.
- Serving-run-name lookup is a conflict check for non-terminal runs only. Terminal conflicting runs follow normal run submission semantics: the run apply path can delete/recreate them, while endpoint code must not adopt/delete unrelated runs by name.
- No generic server-side endpoint health probe in v1. Existing service probes/registration are the server readiness source. In the agent path, the agent itself must perform final functional verification before reporting a final candidate.
- Automatic provisioning retry is Later. A failed endpoint is terminal for v1.
- Frontend UI is explicitly Later; no UI is required for v1.
- `DSTACK_AGENT_ANTHROPIC_API_KEY` remains the official server-agent env var. A local `DSTACK_ANTHROPIC_API_KEY` must be mapped/exported to that name if used.
- The raw `anthropic` Messages API loop is explicitly rejected for the real agent path. The next implementation must use a real agent runtime and package its dependencies automatically for server installs and Docker images.

---

## 1. What we're building

A new top-level dstack configuration type `endpoint`: the user declares *what model* they want served; dstack figures out *how* — either from a locally stored preset (one tested service deployment topology on ordered tested replica spec groups) that matches the project's existing fleets, or by launching an LLM agent (Anthropic) that authors and deploys a dstack service for that model. The endpoint follows the backing service lifecycle instead of adding a parallel serving layer.

```yaml
type: endpoint
name: qwen3-32b          # optional; auto-generated if omitted
model: Qwen/Qwen3-32B    # required; HF model id / model name
env:
  - HF_TOKEN             # merged into whatever service gets deployed
# plus any ProfileParams: backends, regions, spot_policy, max_price, fleets, idle_duration, ...
```

```
dstack apply -f endpoint.dstack.yml
 └─ endpoint: SUBMITTED
     └─ server background pipeline picks it up (multi-replica safe)
         ├─ preset matches existing fleets?  → submit service run from preset
         ├─ else, agent enabled (DSTACK_AGENT_ANTHROPIC_API_KEY)? → agent deploys a service
         └─ else → FAILED ("no matching preset found and server agent disabled")
     └─ endpoint: CLAUDING (agent investigates/deploys, for no-preset agent path)
     └─ endpoint: PROVISIONING (service run starting, model pulling, service probes passing)
     └─ endpoint: RUNNING (service has a registered running job and model URL)
```

The endpoint's deliverable is an OpenAI-compatible base URL (from the backing service's `ServiceSpec.model.base_url`).

### v1 scope (this plan)

- New configuration type + DB model + REST API + CLI (`dstack apply`, `dstack endpoint list|get|logs|stop|preset`).
- `EndpointPipeline` background processing: SUBMITTED → CLAUDING/PROVISIONING → RUNNING/FAILED, STOPPING → STOPPED, crash recovery, and ownership-safe reconciliation.
- Preset subsystem: `EndpointPresetService` interface + local-directory implementation for storing/loading presets; endpoint planning code separately matches loaded presets against existing fleets, including elastic fleets that can provision new instances, via the run planner; successful agent deployments are saved back as sanitized local presets.
- Agent subsystem: `AgentService` interface + real Claude agent runtime implementation, a CLI-first execution workspace that lets the agent use the real `dstack` binary, vendored prompt/context, recipe/hardware grounding, and a minimal structured handoff for the final candidate. Raw LLM API loops are not accepted for v1.
- Endpoint readiness follows the backing dstack service lifecycle on the server side: a service run is usable once it is RUNNING, has a registered running job, and exposes a model URL. The agent path additionally requires the agent to verify the final candidate with a model request before reporting success; the server does not add a generic duplicate endpoint probe in v1.
- `DSTACK_AGENT_ANTHROPIC_API_KEY` + related settings; real agent runtime dependencies installed automatically by normal server install and Docker deployment paths.
- Endpoint apply/log UX: `dstack apply -f endpoint.dstack.yml` shows an advisory plan and confirmation first, then follows endpoint progress by polling server-side status/log storage; `dstack endpoint logs <endpoint>` shows endpoint agent/progress logs, while backing service logs remain available via top-level `dstack logs <service-run-name>`. No frontend UI in v1.

Everything else → §12 "Later".

---

## 2. Ground truth: existing machinery we build on

These are the load-bearing facts a developer needs; each was verified in code.

1. **Configuration registration hub** — `src/dstack/_internal/core/models/configurations.py`: `ApplyConfigurationType` enum, `AnyApplyConfiguration`, `BaseApplyConfiguration.__root__` (discriminated on `type`), `AnyDstackConfiguration` (feeds the editor JSON schema built in CI). CLI dispatch via `apply_configurators_mapping` in `src/dstack/_internal/cli/services/configurators/__init__.py`. There is **no generic server-side apply endpoint** — every resource type has its own typed router + `APIClient` group.
2. **Non-run resource blueprint** — gateways and volumes show the durable pipeline pattern: model with `PipelineModelMixin` (`lock_expires_at`/`lock_token`/`lock_owner`, `models.py:204`) + `status`/`status_message`/`last_processed_at`; status enum in core models; service module (`services/volumes.py` is the cleanest); `Pipeline` subclass registered in `PipelineManager.__init__` (`background/pipeline_tasks/__init__.py:35-48`); router + schemas; configurator. Gateways/volumes also use an async delete flag, but endpoints intentionally do not expose delete in v1; endpoint lifecycle is stop/history.
3. **Multi-replica safety** is NOT the in-memory locker (`services/locking.py` — no-op `DummyResourceLocker` on Postgres by design). It is: durable lock columns claimed in the fetch transaction with `SELECT ... FOR UPDATE SKIP LOCKED`, a `Heartbeater` that checks tracked items every ~1s and extends `lock_expires_at` whenever a lease comes within `heartbeat_trigger` of expiry (so with 30s timeout / 15s trigger, ~every 15s), and every subsequent write guarded by `WHERE id = :id AND lock_token = :token`. If a replica dies, the lease expires (≤ ~30s) and another replica's fetcher re-claims the row (`or_(lock_expires_at.is_(None), lock_expires_at < now)`, ordered by `last_processed_at ASC`). Long operations are legitimate: the heartbeater extends the lease indefinitely (`instances/cloud_provisioning.py` runs minutes-long provisioning inside one `process()` call), but crash recovery restarts the whole step — so steps must be reconcile-first/idempotent.
4. **Server-side run creation is first-class** — `src/dstack/_internal/server/services/runs/__init__.py`: `submit_run(session, user, project, run_spec, pipeline_hinter=None) -> Run`, `stop_runs(...)`, `delete_runs(...)`, `get_run_by_name(...)`, `get_plan(session, project, user, run_spec, max_offers)`. Repo-less runs work: leave `run_spec.repo_id`/`repo_data` as `None` → `validate_run_spec_and_set_defaults` (`runs/spec.py`) fills the virtual repo (`DEFAULT_VIRTUAL_REPO_ID = "none"`) and `_get_run_repo_or_error` upserts the `RepoModel` row. Requires `run_spec.ssh_key_pub` or `user.ssh_public_key` set — and note `get_plan` calls the same validation, so this bites at *planning* time too. `submit_run` **commits the session multiple times** — always call it (and `stop_runs`/`delete_runs`) with a fresh `get_session_ctx()`, never inside a pipeline worker's token-guarded transaction.
5. **Run teardown is asynchronous and two-phase.** `stop_runs` only sets `termination_reason` + status `TERMINATING`; the RunPipeline performs actual termination. `TERMINATING` is **not** in `RunStatus.finished_statuses()` (`[TERMINATED, FAILED, DONE]`), and `delete_runs` raises `ServerClientError("Cannot delete active runs: ...")` for any non-finished run. Neither function raises for missing names — they filter and silently no-op. **Any "stop then delete" flow must wait (across pipeline iterations) for the run to finish before deleting.**
6. **Service readiness ≠ `RunStatus.RUNNING`.** A run is RUNNING when *any* replica job is RUNNING (`pipeline_tasks/runs/active.py`). The service-level readiness signal is `JobModel.registered`, set `True` only after all service probes pass (`_maybe_register_replica`, `jobs_running.py:1158`; it is set back to `False` only in the terminating pipeline, `jobs_terminating.py:787`). If `model:` is set and `probes` omitted, a default `POST {prefix}/chat/completions` probe is auto-generated (`services/jobs/configurators/base.py::_openai_model_probe_spec`). Endpoint v1 relies on this existing service mechanism instead of adding a parallel endpoint probe loop.
7. **In-process model probing exists but is not generic endpoint v1 behavior** — `_execute_probe` (`background/scheduled_tasks/probes.py:106-126`) POSTs `chat/completions` to a replica through `get_service_replica_client(job_model)` (`services/jobs/job_replica_http_client.py`, SSH tunnel + httpx over a Unix socket; URL host is a dummy `http://dstack`; the whole call is wrapped in `except (SSHError, httpx.RequestError) → False`). This is useful background for later agent verification/hardening, but v1 endpoint readiness should not duplicate service probes.
8. **Preset↔fleet matching primitive** — `_get_job_plan` (`services/runs/plan.py:970-988`): plan offers always include existing-instance offers, and add new-cloud offers only when `profile.creation_policy == CreationPolicy.REUSE_OR_CREATE` **and** `profile.instances is None`. This is exactly the "existing fleets" semantics we need: a non-empty available offer can mean either an already-idle instance or an elastic fleet that can create a new matching instance. If the user explicitly sets `creation_policy: reuse`, matching is restricted to currently existing instances; otherwise the default `reuse-or-create` allows elastic fleet capacity. (Caveats: each candidate evaluation can take seconds because the planner enumerates offers; and the per-job criterion under-checks total capacity for multi-replica configs — see §7.3.)
9. **No system user exists.** Only `admin` is guaranteed (`services/users.py::get_or_create_admin_user`, created at startup). Runs are only ever **soft-deleted** (`delete_runs` sets `RunModel.deleted=True`; nothing hard-deletes run rows except the project-cascade) — an `ondelete=SET NULL` on a run FK effectively never fires; handlers must treat `run.deleted == True` as "run gone". `RunModel` has no tags column; for endpoints, the serving run uses an explicit FK (`service_run_id`) and endpoint-submitted run history lives in `EndpointRunSubmissionModel`. Name/user/timestamp checks are not a durable ownership model.
10. **Packaging baseline**: hatchling normally packages `src/dstack` plus declared artifacts; repo-root `skills/` must be force-included explicitly or an installed server will not have them. This branch force-includes `skills/**` for wheels/sdists and keeps the endpoint-specific system prompt under `src/dstack`. **dstack pins `pydantic>=1.10.10,<2.0.0`** — do not import an agent runtime that requires pydantic v2 into the server process (§8.2).
11. **Agent skills live under repo-root `skills/`** — `skills/dstack/SKILL.md` and `skills/dstack-prototyping/SKILL.md` are the canonical skill files. `pyproject.toml` packages `skills/**` into wheels/sdists, and the endpoint harness locates that packaged `skills` directory before copying the required skills into each agent workspace's `.claude/skills`.
12. **A "templates" feature already exists** (`core/models/templates.py::UITemplate`, `services/templates.py`, `DSTACK_SERVER_TEMPLATES_REPO`) — UI-only, git-repo-sourced run-config templates. Presets must not collide with this namespace (we use "preset" consistently); reusing its git-repo fetch machinery is a Later option.
13. **External recipes**: vLLM recipes expose a machine-readable JSON API built for agents — `https://recipes.vllm.ai/models.json` (index, ~500 entries, dedupe on `derived_from`) + `https://recipes.vllm.ai/<hf_org>/<hf_repo>.json` (exact `vllm serve` command, docker image, per-GPU configs). SGLang Cookbook lives at `docs.sglang.io/cookbook` (source: `sgl-project/sglang:docs_new/cookbook`, MDX; discoverable via `https://docs.sglang.io/llms.txt`; pages fetchable raw by appending `.md`, but some embed commands in JSX). Both Apache-2.0 — runtime fetching and vendoring with attribution are fine. The old `sgl-cookbook` repo is archived read-only.
14. **Research notes behind this plan are now stored in-repo** under `endpoint-implementation-research/`, copied from `/private/tmp/claude-501/-Users-dstack-dstack/b621b4a9-b6ee-4b6b-813e-1084018def84/scratchpad/research/` plus `verify-findings.md`. These are planning artifacts, not packaged runtime resources; the packaged endpoint prompt and skills live under `src/dstack/_internal/server/services/endpoints/agent/` (§8.4).

---

## 3. Configuration & core models

New file `src/dstack/_internal/core/models/endpoints.py`:

```python
class EndpointStatus(str, Enum):
    SUBMITTED = "submitted"
    PROVISIONING = "provisioning"
    CLAUDING = "clauding"      # server agent is investigating/deploying
    RUNNING = "running"        # backing service is ready
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"

class EndpointConfiguration(ProfileParams, generate_dual_core_model(EndpointConfigurationConfig)):
    type: Literal["endpoint"] = "endpoint"
    name: Optional[str] = None          # dstack resource name; auto-generated if omitted
    model: str                          # required; HF model id / served model name
    env: Env = Env()

class Endpoint(CoreModel):              # API/runtime representation
    id: uuid.UUID
    name: str
    project_name: str
    user: str
    configuration: EndpointConfiguration
    created_at: datetime
    status: EndpointStatus
    status_message: Optional[str]
    run_name: Optional[str]             # backing service run (if provisioned)
    url: Optional[str]                  # OpenAI-compatible base URL from ServiceSpec.model.base_url (read-time derived)
    error: Optional[str]
```

Notes:
- `ProfileParams` (`core/models/profiles.py:310-493`) gives us `backends/regions/spot_policy/max_price/creation_policy/idle_duration/fleets/tags/...` for free — this is exactly the "profile params" requirement. Follow the run-config MRO pattern (`ProfileParams` first) and the pydantic-duality rule: never define `class Config` directly; create `EndpointConfigurationConfig(ProfileParamsConfig)` chaining `schema_extra` and pass it via `generate_dual_core_model(...)` as the last base (see `ServiceConfigurationConfig`, `configurations.py:1316`).
- Codebase is **pydantic v1** (`validator`/`root_validator`, `.json()`/`.parse_raw()`); do not write v2 APIs.
- No `EndpointSpec` type in v1 — `CreateEndpointRequest` takes a bare `configuration` (volumes parity, `CreateVolumeRequest`); introduce a spec wrapper together with the plugins work (§12) if/when needed.
- `Env` is a plain BaseModel with a custom root (`core/models/envs.py`) — bare `VAR` entries are `EnvSentinel`s resolved from `os.environ` **CLI-side only** (`ApplyEnvVarsConfiguratorMixin.apply_env_vars`). The server must reject configurations arriving with unresolved sentinels (validate in `create_endpoint`; `Env.as_dict()` raises `ValueError` on unresolved).
- Validate `name` with `validate_dstack_resource_name` (regex `^[a-z][a-z0-9-]{1,40}$`, `core/services/__init__.py`). `model` is deliberately a plain `str` in v1 (not `AnyModel`) — it's a requirement, not a service config field.

**Registration checklist** (all in `core/models/configurations.py` unless noted):
1. Add `ENDPOINT = "endpoint"` to `ApplyConfigurationType` (~:1384).
2. Add `EndpointConfiguration` to `AnyApplyConfiguration` (~:1393).
3. Add it to `BaseApplyConfiguration.__root__` union (~:1401) — it's a "final configuration" (single `type` discriminator; no second-stage parse like volumes).
4. Add it to `AnyDstackConfiguration` (~:1440) — the editor JSON schema in CI (`.github/workflows/build-artifacts.yml`, `DstackConfiguration.schema_json()`) picks it up automatically.
5. Watch for circular imports: `configurations.py` already imports fleets/gateways/volumes models the same way.

---

## 4. DB model, migration, events

`src/dstack/_internal/server/models.py` — follow the normal pipeline model shape, but do not copy volume soft-delete semantics: endpoints have stop/stopped, not delete.

```python
class EndpointModel(PipelineModelMixin, BaseModel):
    __tablename__ = "endpoints"

    id:            UUIDType(binary=False) pk, default=uuid.uuid4
    name:          Mapped[str] = mapped_column(String(100))
    project_id:    FK("projects.id", ondelete="CASCADE") + relationship
    user_id:       FK("users.id", ondelete="CASCADE") + relationship   # endpoint creator; runs are submitted as this user
    service_run_id: Mapped[Optional[uuid.UUID]] = FK("runs.id") + relationship
    """The service run currently backing this endpoint (authoritative link; run name is convention only).
    Runs are soft-deleted, so handlers must treat run.deleted == True as 'run gone' — no ondelete magic applies."""
    configuration: Mapped[str] = mapped_column(Text)                   # EndpointConfiguration JSON
    status:        Mapped[EndpointStatus] = mapped_column(EnumAsString(EndpointStatus, 100), index=True)
    """Must be changed only via switch_endpoint_status() (API side) / token-guarded pipeline updates."""
    status_message: Mapped[Optional[str]] = mapped_column(Text)
    provisioning_method: Mapped[Optional[str]] = mapped_column(String(100))   # "preset:<name>" | "agent"; NULL until dispatched
    created_at:    NaiveDateTime, default=get_current_datetime
    last_processed_at: Mapped[datetime] = mapped_column(NaiveDateTime)  # MUST equal created_at on insert (fetch fast-path)

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_endpoints_project_id_name"),
        Index("ix_endpoints_pipeline_fetch_q", last_processed_at.asc()),
    )
```

- One row per `(project_id, name)`. There is no endpoint soft delete in v1. Terminal same-name reapply resets the existing row and `EndpointRunSubmissionModel` preserves backing run submission history.
- JSON goes in `Text` columns as pydantic JSON — there is no JSON column type in this codebase.
- **Migration**: one new table, one migration. Generate with `cd src/dstack/_internal/server && alembic revision -m "add endpoints" --autogenerate`; lands under `migrations/versions/2026/` (per `alembic.ini` `file_template`). Plain `op.create_table` (a new table is additive ⇒ zero-downtime-safe; `contributing/MIGRATIONS.md`'s "separate migrations per table" rule concerns ALTERs of existing tables, and its `CREATE INDEX CONCURRENTLY` guidance applies to existing tables only). Column types: `sqlalchemy_utils.types.uuid.UUIDType(binary=False)`, `dstack._internal.server.models.NaiveDateTime()`. Remember tests create schema via `metadata.create_all`, so a *missing* migration won't fail unit tests — the migration is its own review item.
- **Events**: add `ENDPOINT` to `EventTargetType` (`core/models/events.py:12`) and an `EndpointModel` branch to `events.Target.from_model` (`server/services/events.py:89`) — `from_model` raises `ValueError` for unregistered types, so forgetting this crashes the first `emit()`.

---

## 5. Server service module, REST API, CLI

### 5.1 Service module — `src/dstack/_internal/server/services/endpoints/` (package: `__init__.py`, `presets.py`, `planning.py`, `agent/`)

- `create_endpoint(session, project, user, configuration, pipeline_hinter) -> Endpoint`:
  validate name + reject unresolved `EnvSentinel`s → name-uniqueness critical section (`lock_namespace = f"endpoint_names_{project.name}"`; SQLite: commit first + in-process lockset; Postgres: `pg_advisory_xact_lock(string_to_lock_id(ns))`) → duplicate non-terminal name ⇒ `ResourceExistsError` → duplicate terminal name ⇒ reset the same row to `SUBMITTED` with the new config, clear `service_run_id`/status message/provisioning method/lock fields, and refresh `created_at == last_processed_at == now` → auto-name via `generate_name()` loop if unset → insert row with `status=SUBMITTED`, `created_at == last_processed_at == now` → emit create/submit event → commit → `pipeline_hinter.hint_fetch(EndpointModel.__name__)`.
- `stop_endpoints(session, project, names, user)`: set `status=STOPPING` for non-finished endpoints, emit a stop event, commit, and `hint_fetch`. The pipeline owns stopping the linked backing service run and marking the endpoint `STOPPED`.
- `list_endpoints` (keyset pagination on `(created_at, id)` like volumes), `get_endpoint_by_name`, `endpoint_model_to_endpoint` (parse config via `EndpointConfiguration.__response__.parse_raw`; populate `run_name`/`url` at read time from the joined run's `service_spec` when present), `switch_endpoint_status(session, endpoint_model, new_status, actor=SystemActor())` + `emit_endpoint_status_change_event`.
- v1 does **not** call `apply_plugin_policies` — `ApplySpec` TypeVar (`dstack/plugins/_models.py:8`) doesn't include endpoints; extending it is a Later item (do not call the function with an unsupported type).

### 5.2 REST API

- `src/dstack/_internal/server/schemas/endpoints.py`: `ListEndpointsRequest`, `GetEndpointRequest{name}`, `GetEndpointPlanRequest{configuration, configuration_path?}`, `CreateEndpointRequest{configuration: EndpointConfiguration}`, `StopEndpointsRequest{names}` (all `CoreModel`).
- Endpoint configuration includes `preset_policy` (`reuse`, `create`, `reuse-or-create`, default `reuse-or-create`). This is distinct from profile `creation_policy`: `preset_policy` chooses whether endpoint provisioning may reuse a tested service recipe or ask the server agent to create one; `creation_policy` still controls whether the resulting service can reuse existing instances or provision new ones from elastic fleets.
- New core model `EndpointPlan`: `project_name`, `user`, `configuration`, `configuration_path`, `current_resource`, `action`, `preset_policy`, and `provisioning_plan`. `preset_policy` is the configured/default policy shown in the CLI; the selected path (`preset`, `agent`, or `none`) belongs in `provisioning_plan`.
- `provisioning_plan` is a small discriminated union:
  - `type="preset"`: a **provisionable preset** was selected. This includes `preset_name`, `service_name`, `replica_spec_groups: list[EndpointPlanReplicaSpecGroup]`, and `job_offers: list[EndpointPlanJobOffers]` derived from `runs.get_plan` (enough for the CLI to print the selected preset, stable run-like scheduling properties, and first matching offers, without dumping the full run plan).
  - `type="agent"`: no provisionable preset was found and the policy allows creation. The plan may include a short reason such as "matching preset qwen has no available offers"; the initial plan must not invent final offers because the agent may explore hardware and service shapes within endpoint/profile constraints.
  - `type="none"`: no provisionable path is available, with the exact failure message that the pipeline will use (for example, `preset_policy: reuse` with no matching preset or only no-offer presets, or `preset_policy: reuse-or-create` with no provisionable preset and no usable server agent).
- Preset terminology:
  - A **model-matched preset** has the requested model and can be parsed/planned.
  - A **provisionable preset** is a model-matched preset whose run plan has at least one available offer for every job plan.
  - Only provisionable presets are submitted automatically. A no-offer preset is shown as context; if `preset_policy: reuse-or-create` and the agent is available, the pipeline falls through to the agent path instead of submitting the doomed preset. With `preset_policy: reuse`, no-offer presets stop with the normal no-offers/no-fleets UX.
- Plan semantics are advisory. `/get_plan` runs the same preset matching code and agent-enabled check that the pipeline will run, but the pipeline re-evaluates after submit because fleets/presets/agent availability may change. This mirrors run apply's UX without introducing endpoint in-place update in v1.
- `src/dstack/_internal/server/routers/endpoints.py`: `project_router = APIRouter(prefix="/api/project/{project_name}/endpoints", tags=["endpoints"], responses=get_base_api_additional_responses())` with `/list`, `/get`, `/get_plan`, `/create`, `/stop`. **Permission: `ProjectMember()`** (volumes precedent — endpoints are project workloads like runs, not admin infra like gateways). `/create` and `/stop` take `pipeline_hinter: Annotated[PipelineHinterProtocol, Depends(get_pipeline_hinter)]`. Responses via `CustomORJSONResponse`.
- Register in `server/app.py::register_routes` next to volumes (~:257).
- API client: `src/dstack/api/server/_endpoints.py` `EndpointsAPIClient(APIClientGroup)` (`list/get/get_plan/create/stop`, parse with `parse_obj_as(Endpoint.__response__, ...)`) + `endpoints` property on `APIClient` (`api/server/__init__.py`).
- No endpoint `/apply_plan` in v1: submit remains `/create`, and changed existing endpoints are handled by CLI-requested stop/override. The CLI requests endpoint stop and polls until the endpoint is terminal; the next `/create` resets the same endpoint row to `SUBMITTED` with the new config. In-place update/rolling redeploy is Later.

### 5.3 CLI

- `src/dstack/_internal/cli/services/configurators/endpoint.py`: `EndpointConfigurator(ApplyEnvVarsConfiguratorMixin, BaseApplyConfigurator)` with `TYPE = ApplyConfigurationType.ENDPOINT`. Model on `VolumeConfigurator`:
  - `apply_configuration`: resolve env sentinels (`apply_env_vars`), call `api.client.endpoints.get_plan(...)`, print the endpoint plan, confirm, then `api.client.endpoints.create(...)`; on name collision: if the existing endpoint has the same config, print no changes and exit unless `--force`; if the config changed, show that the endpoint and its backing service will be stopped and replaced, then require confirmation (or `-y`) before calling `endpoints.stop`, polling until the endpoint becomes terminal, and creating a fresh endpoint. The CLI must not stop backing runs directly. This mirrors run apply's "stop and override" v1 behavior, not an in-place update; in-place update/rolling redeploy is Later (§12).
  - Plan output: keep it close to run apply. Print one stable properties table: project, user, configuration path, type, spot policy, max price, preset policy, and preset name only when a provisionable preset was selected. Do not show model, action, endpoint name as a separate row, resources as a separate property, backing service name, agent internals, or a separate "Provisioning" section. If a provisionable preset matched, print offers underneath using the run-style offers table; that offers table is where the concrete resource information belongs. If only no-offer presets matched, print one short message below the table; with `reuse-or-create` and an available agent, continue to the agent path.
  - TODO: For `preset_policy: create` or agent fallback, `dstack apply` may later show initial candidate offers the agent can consider. These offers are advisory only: they must not be presented as selected endpoint resources or final hardware because the agent may still choose a different working service shape after investigation.
  - Non-detached apply should **imitate attached progress without using attach**: poll `endpoints.get` for status and stream the endpoint's own progress log stream. Do not reserve local ports, open SSH tunnels, or call `run.attach`. Backing service stdout/stderr remains available through `dstack logs <service-run-name>`.
  - Detached apply (`-d`) submits and exits with the normal `submitted, detaching...` message. Follow-up commands (`dstack endpoint list`, `dstack endpoint get <name> --json`, and `dstack endpoint logs <name>`) are documented/help text, not extra foreground hints.
  - `delete_configuration`: unsupported for endpoints. `dstack delete -f endpoint.dstack.yml` should fail clearly and point to `dstack endpoint stop <name>`.
  - Provisioning can take tens of minutes (model pulls, agent runs), so `-d` should work exactly as with runs. Keep foreground output concise; document follow-up commands in help/docs.
- Register in `apply_configurators_mapping` (`cli/services/configurators/__init__.py:27-49`). `dstack apply` and `dstack apply -h endpoint` then work with no further CLI edits; `dstack delete -f endpoint.dstack.yml` is explicitly rejected by `EndpointConfigurator.delete_configuration`.
- `src/dstack/_internal/cli/commands/endpoint.py`: `EndpointCommand` (`dstack endpoint list` / `get --json` / `logs` / `stop` / `preset list|get --json|delete`); register in `cli/main.py`.
- Nice property to document: preset-backed endpoints use a readable endpoint-derived service run name (normally `<endpoint>-serving`). Agent-backed endpoints may use a different concise run name chosen during investigation; once linked, backing service logs are available by the linked run name.

### 5.4 Endpoint logs

Support endpoint logs in v1, but only via detached/server-side log polling:

- Add `dstack endpoint logs <name>`. Top-level `dstack logs` remains run-only so same-name endpoint/run collisions do not silently show the wrong stream. Endpoint logs are concise agent/pipeline progress events, not backing service stdout/stderr.
- Do not introduce `dstack attach` for endpoints in v1. Endpoint apply/logs must use configured log storage (`FileLogStorage`, CloudWatch, GCP Logging, Fluent Bit/Elasticsearch, etc.) via the existing server log service. Backing service logs remain normal run logs and are requested with the service run name.
- The agent should emit major progress events to the endpoint log stream in real time. Detailed command output/transcripts stay in the endpoint workspace/debug trace so server logs and endpoint logs do not fill with huge YAML or CLI output.
- Tests: `dstack endpoint logs` reads the endpoint stream and does not fall through to the backing service run; top-level `dstack logs` remains run-only; non-detached endpoint apply does not call `run.attach`.

---

## 6. Background processing: `EndpointPipeline`

New file `src/dstack/_internal/server/background/pipeline_tasks/endpoints.py`, cloned from `volumes.py` (the cleanest single-model pipeline), registered in `PipelineManager.__init__` (`background/pipeline_tasks/__init__.py:35-48`).

### 6.1 Pipeline wiring

- `EndpointPipelineItem(PipelineItem)` + `{status}`; `EndpointPipeline(Pipeline[EndpointPipelineItem])`, `hint_fetch_model_name -> EndpointModel.__name__`.
- Tuning: `workers_num=4` (each in-flight agent run occupies a worker for minutes — this is the per-replica concurrency bound for paid agent sessions), `min_processing_interval=10s`, `lock_timeout=30s`, `heartbeat_trigger=15s`. The `Heartbeater` extends the lease indefinitely during a long `process()` call (precedent: `instances/cloud_provisioning.py`), so minutes-long agent steps are safe while the replica lives.
- `EndpointFetcher.fetch` — copy the volume fetch query shape, with the endpoint status filter and a longer effective interval for RUNNING rows (precedent: `InstanceFetcher`, `instances/__init__.py:190-211`, uses `min_processing_interval * 2` for steady-state statuses; we use a larger multiplier via an explicit condition):
  - `WHERE status IN (SUBMITTED, CLAUDING, PROVISIONING, STOPPING) OR (status == RUNNING AND last_processed_at <= now - ENDPOINT_RUNNING_CHECK_INTERVAL)`
  - `AND (last_processed_at <= now - min_processing_interval OR last_processed_at == created_at)`
  - `AND (lock_expires_at IS NULL OR lock_expires_at < now)`
  - `AND (lock_owner IS NULL OR lock_owner == EndpointPipeline.__name__)`
  - `ORDER BY last_processed_at ASC LIMIT :limit FOR UPDATE SKIP LOCKED (key_share)`
  - claim: one `lock_token` per batch, `lock_expires_at = now + lock_timeout`, `lock_owner = EndpointPipeline.__name__`; commit.
- `EndpointWorker.process`: refetch by `(id, lock_token)` with joinedloads — **must include `EndpointModel.project → ProjectModel.backends`** (in addition to `user` and `service_run`): the preset-matching path reaches `get_project_backends(project)`, which iterates the lazy `project.backends` relationship and raises `MissingGreenlet` under async SQLAlchemy if not eager-loaded (established pattern: `background/pipeline_tasks/volumes.py:237`, `gateways.py:232`). On token mismatch `log_lock_token_mismatch`; dispatch by state; build `_EndpointUpdateMap(ItemUpdateMap)` (adds `status`, `status_message`, `service_run_id`, `provisioning_method`); final write via `update(EndpointModel).where(id==..., lock_token==...).values(**update_map).returning(id)` after `set_processed_update_map_fields` + `set_unlock_update_map_fields` + `resolve_now_placeholders`; 0 rows ⇒ `log_lock_token_changed_after_processing` and abandon. Emit status-change events in the same transaction. Instrument with `@sentry_utils.instrument_pipeline_task(...)`.

**Transaction rule (critical):** run submission/termination (`submit_run`, `stop_runs`, `delete_runs`) commit their own sessions and take their own advisory locks. The worker must call them through a **fresh `get_session_ctx()`**, never inside its own fetch/update session. Interleaving is safe because the endpoint row itself stays lease-locked.

**Interim token-guarded updates:** if the agent path needs to persist progress before a long agent call, use an interim `UPDATE ... WHERE id AND lock_token` (+ commit). This is mechanically consistent with the framework (it leaves the lock columns untouched, so the heartbeater and the final write are unaffected; precedent for mid-process commits: related-row lock claims in `fleets.py` / `jobs_submitted.py`) — but the handler must then make sure the final update map doesn't overwrite interim values with stale ones.

### 6.2 State machine

```
SUBMITTED ──(preset selected; deterministic service run name is taken)──► FAILED "run name '<n>' is taken by an existing run"
SUBMITTED ──(preset matched; run submitted)───────► PROVISIONING (method=preset:<n>)
SUBMITTED ──(no preset, agent on)─────────────────► CLAUDING (method=agent)
SUBMITTED ──(preset_policy=reuse; no preset)──────► FAILED "No matching endpoint presets found."
SUBMITTED ──(effective policy=create; agent off)──► FAILED "No matching endpoint presets found. Preset
                                                            policy create requires the server agent,
                                                            but DSTACK_AGENT_ANTHROPIC_API_KEY is not set."
CLAUDING ─(agent reports verified service run; run not ready yet)──► CLAUDING (service_run_id linked)
CLAUDING ─(linked run RUNNING + replica registered + model URL)────► RUNNING
PROVISIONING ─(preset run RUNNING + replica registered + model URL)► RUNNING
PROVISIONING ─(run finished/soft-deleted)──────────────────────────► FAILED
RUNNING ─(run gone/failed/deleted)─────────────────────────────────► FAILED (stop backing run)   # later: agent retry policy
any ─(stop requested)──────────────────────────────────────────────► STOPPING → stop linked backing run → STOPPED
```

V1 does **not** automatically retry failed provisioning attempts. A backing run that finishes or fails before readiness makes the endpoint FAILED.

#### `_process_submitted_endpoint`
1. Parse `EndpointConfiguration`; ask endpoint planning code (`planning.py::find_matching_preset_plan(...)`) to list presets through `EndpointPresetService`, build candidate run specs, and call the run planner (§7).
2. If a provisionable preset matches: check the run name in that selected plan. A non-terminal run conflict that is not the linked `service_run_id` fails with a clear message; terminal conflicts are left to normal run submission, which can recycle them like service apply. Then submit the matching plan in a fresh session as the endpoint's creator user through a small internal helper that mirrors the run router (`refresh_ssh_key` if needed, `get_plan`, then `apply_plan`/`submit_run` with the same policy-applied spec), and return `{status: PROVISIONING, provisioning_method: f"preset:{preset.name}", service_run_id: run.id}`. `register_service` runs synchronously during submission and can raise (`FORBID_SERVICES_WITHOUT_GATEWAY`, referenced gateway missing) — catch `ServerClientError` ⇒ FAILED with the message.
3. Else if agent enabled (`settings.AGENT_ANTHROPIC_API_KEY` set and the real agent runtime is available): return `{status: CLAUDING, provisioning_method: "agent"}` — the agent runs in the CLAUDING handler (keeps SUBMITTED processing fast and makes long agent work visible in CLI/API). Do not block this path on the preset path's deterministic service-run-name convention; the agent may use its own concise candidate/final run names, and the server links the final run by ID after validating project/user/config.
4. Else FAILED (message above; if the key is set but the runtime is unavailable, say the server agent implementation/runtime is unavailable; normal server installs and Docker images must include runtime dependencies once the implementation lands).

#### `_process_provisioning_endpoint` — reconcile-first
1. **If `service_run_id` set**, load the run (treating `run.deleted == True` as "run gone"):
   - run `RUNNING`, ≥1 replica job with `registered == True`, and `ServiceSpec.model.base_url` exists → if `provisioning_method == "agent"`, save a sanitized preset from the backing run (§7.4), then `RUNNING`. This deliberately relies on the existing service probe/registration path rather than adding a second endpoint probe.
   - run in `finished_statuses()` or soft-deleted → FAILED with the run error/status. Automatic retry is Later.
   - run `TERMINATING` → no-op (wait).
   - run still starting (SUBMITTED/PROVISIONING/PULLING) → no-op; stay PROVISIONING.
3. **CLAUDING / no run yet + method=agent** — the long step:
   a. Needed hardening: before launching or relaunching the agent, reconcile the endpoint workspace, existing final-report artifacts, endpoint submission rows, and live candidate/final runs. Without this, a server restart can start a fresh agent process for an endpoint whose previous agent process had already submitted work but had not linked `service_run_id` yet. Cleanup of endpoint-submitted runs must use explicit `EndpointRunSubmissionModel` rows, never name matching.
   b. Run `AgentService.provision_endpoint(...)` (§8) inside the worker — heartbeater keeps the lease alive while the agent subprocess runs. V0 still needs stop-time cancellation and restart-safe recovery: stop can mark the endpoint `STOPPING`, but the worker must learn to stop/abort the live agent process instead of waiting for it to exit naturally. Do not add a generic endpoint provisioning timeout here; real agent-session budgets belong inside the harness once token/cost/spend semantics are defined.
   c. On structured success `{run_id}`/linked service run → set `service_run_id` and keep status `CLAUDING` until the linked service run also satisfies normal dstack service readiness. Once ready, save the learned preset and mark the endpoint `RUNNING`. On failure/abort → FAILED with the agent's summary in `status_message` + stop only the linked service run; cleanup of non-final candidate runs must use explicit endpoint submission records, not name matching.
4. **No run yet + method=preset**: reachable only if the preset run vanished before the endpoint recorded its linked service run — FAILED. Automatic retry is Later.

#### `_process_running_endpoint`
Runs at the slower RUNNING cadence (`ENDPOINT_RUNNING_CHECK_INTERVAL`, default 60s):
1. Run liveness: backing run missing/soft-deleted/`finished_statuses()`/`TERMINATING` ⇒ FAILED "Backing service run <name> is <status>" (v1; re-provisioning is a Later "agent retry policy" item). This also catches out-of-band `dstack stop`/`delete` of the run by users.
2. No generic server-side endpoint model probe in v1. The backing service owns probes and registration for lifecycle readiness. In the agent path, the agent must make a final model request and include the result in its final report before the server links the candidate.

**Rule: every transition to FAILED issues a one-shot `stop_runs(abort=False)` for a still non-terminal backing run** (RunPipeline completes the termination asynchronously; no waiting needed since FAILED endpoints aren't re-fetched). Stopping a FAILED endpoint later is a no-op unless a linked run still needs cleanup.

#### `_process_stopping_endpoint`
Two-phase, server-side, and intentionally simple in v1: (1) backing run present and not finished → `stop_runs(abort=False)` once, then no-op wait on subsequent iterations while the normal RunPipeline terminates the run. (2) run finished (or absent/deleted) → write `{status: STOPPED}`, keep the endpoint row visible in history, and emit "Endpoint stopped". Forced abort/escalation for stuck stopping is Later, not required for v1.

### 6.3 Crash recovery summary

Replica dies mid-step ⇒ heartbeats stop ⇒ lease expires (≤ ~30s) ⇒ another replica re-fetches the row. V1 handlers are idempotent around the linked `service_run_id`; preset-run-name conflicts are treated as conflicts, not ownership. `EndpointRunSubmissionModel` preserves endpoint-submitted run history so later agent attempts can recover without relying on names. Agent session budgeting is Later and should be explicit to the agent harness, not a generic endpoint provisioning timeout. Automatic retry is Later.

### 6.4 Endpoint-level model probes (deferred)

Do **not** add a generic endpoint probe loop in v1. Service configurations already own probes, and `JobModel.registered` is the service readiness signal after those probes pass. Adding a second endpoint probe loop duplicates service behavior, introduces token/base-URL/proxy/network ambiguity, and makes endpoint lifecycle less conventional for dstack.

Later, server-side endpoint retry/hardening may add its own explicit verification before re-saving a learned preset or marking an endpoint running again. If/when that is added, prefer reusing the existing in-process probe machinery (`scheduled_tasks/probes.py::_execute_probe` and `get_service_replica_client`) rather than probing through the public service URL.

### 6.5 Run identity & linkage (decision)

- **Backing service run name**: the preset path uses `get_endpoint_serving_run_name(endpoint.name)` (`<endpoint>-serving` when it fits, otherwise the endpoint name) because the server submits that service itself. The agent path may use any concise, unique run name. In both paths, `EndpointModel.service_run_id` is the authoritative link for readiness, URL derivation, logs, and v1 cleanup. Name lookup is not an ownership proof and must not be used to adopt or destroy a run.
- **Endpoint-created run ownership:** `EndpointModel.service_run_id` points to the current/latest service run. `EndpointRunSubmissionModel` records ordered endpoint-submitted run history. Keep `RunModel` endpoint-agnostic.
- Consequences for conservative v1: a non-terminal preset-path service run name not linked by `service_run_id` ⇒ endpoint FAILED with a clear message before preset submission. A terminal conflicting run is handled by the existing run submission path. Agent retry policy and cleanup of non-final agent experiment runs are Later/Path B work.

### 6.6 Endpoint run submissions

`EndpointModel.service_run_id` is the current/latest service run and the ownership link for cleanup/readiness/log fallback. `EndpointRunSubmissionModel` records ordered run history submitted by the endpoint:

```python
class EndpointRunSubmissionModel(BaseModel):
    endpoint_id: uuid.UUID
    run_id: uuid.UUID
    submission_num: int
    submitted_at: datetime
```

Constraints:
- `UNIQUE(run_id)` so a run is recorded for at most one endpoint.
- `UNIQUE(endpoint_id, submission_num)` so submissions are ordered per endpoint.
- Index `endpoint_id` for endpoint history/cleanup lookup.

Rules:
- `EndpointModel.service_run_id` remains the single current serving run.
- `EndpointRunSubmissionModel` is history/provenance for endpoint-submitted runs, not the serving-run selector.
- Preset-path run-name lookup remains conflict detection for non-terminal runs only. CLI/user confirmation may stop that conflicting run, but the background worker must not auto-adopt or auto-delete it by name.

Implementation note:
- `runs.apply_plan()` can commit internally, so endpoint code records the submission immediately after a run is accepted and before moving on. If the agent creates multiple prototype/candidate runs inside one call, its submit tool must record each `EndpointRunSubmissionModel` row before the next submission.

---

## 7. Preset subsystem

Storage and parsing live in `src/dstack/_internal/server/services/endpoints/presets.py`.
Preset matching and run-plan construction live in `src/dstack/_internal/server/services/endpoints/planning.py`.

### 7.1 What a preset is

A preset is **one tested endpoint deployment topology on one tested set of replica spec groups**. It is not a generic service recipe that dstack is free to reshape onto arbitrary GPUs, and it is not a bundle of alternative hardware variants. If the same model is tested on L4 and A10G, that is two presets. If one tested service uses multiple replicas or multiple replica groups, that is still one preset.

In v1 the local file is a small wrapper around:
- `model`: the endpoint model this preset satisfies and the matching key;
- `service`: the serving recipe and service shape (image, commands, port, model mapping, env names, volumes, probes, scaling, replica count/range, or replica groups);
- `replica_spec_groups`: ordered replica groups with one scheduling `resources` value and one `tested_resources` entry per verified running replica.

The wrapper is deliberate: scheduling requirements and placement evidence are separated from the serving recipe in the preset artifact, then compiled into a normal `ServiceConfiguration` before calling the existing run planner. This keeps the stored preset clear without introducing a new provisioning path.

Homogeneous service example (`qwen3-32b-vllm-h100x4.dstack.yml`): no explicit `service.replicas` list means there is one implicit replica group (`"0"`). The loader derives the service's top-level `resources` from the group's `resources` before planning/submission. The group's `tested_resources` records where the replicas actually ran when verified.

```yaml
type: endpoint-preset
model: Qwen/Qwen3-32B
service:
  image: vllm/vllm-openai:latest
  commands:
    - |
      vllm serve Qwen/Qwen3-32B --host 0.0.0.0 --port 8000 \
        --tensor-parallel-size $DSTACK_GPUS_NUM
  port: 8000
  model: Qwen/Qwen3-32B
  env:
    - HF_TOKEN
  volumes:
    - instance_path: /root/.cache
      path: /root/.cache
      optional: true
replica_spec_groups:
  - name: "0"  # optional for the implicit group; stored explicitly when saving
    resources:
      shm_size: 16GB
      gpu: H100:4
    tested_resources:
      - cpu: 64
        memory: 512GB
        disk: 200GB
        gpu: H100:80GB:4
```

Replica-group example: `replica_spec_groups` is sorted in exactly the same order as `service.replicas`, and every group name must match. The loader derives each replica group's service `resources` from the corresponding preset group's `resources`. `tested_resources` records the exact instances that were running when the preset was verified. This supports an existing dstack service shape with different resource specs per group without making v1 responsible for inventing advanced serving architectures.

```yaml
type: endpoint-preset
model: Qwen/Qwen3-32B
service:
  port: 8000
  model: Qwen/Qwen3-32B
  replicas:
    - name: router
      count: 1
      image: ghcr.io/example/router:latest
      commands:
        - python router.py
    - name: worker
      count: 2
      image: vllm/vllm-openai:latest
      commands:
        - vllm serve Qwen/Qwen3-32B --host 0.0.0.0 --port 8000
replica_spec_groups:
  - name: router
    resources:
      cpu: 4
    tested_resources:
      - cpu: 8
        memory: 16GB
        disk: 100GB
        gpu: 0
  - name: worker
    resources:
      shm_size: 16GB
      gpu: H100:4
    tested_resources:
      - cpu: 64
        memory: 512GB
        disk: 200GB
        gpu: H100:80GB:4
      - cpu: 64
        memory: 512GB
        disk: 200GB
        gpu: H100:80GB:4
```

V1 constraints:
- `service` must not contain `name`, `ProfileParams`, top-level `resources`, or replica-group `resources`. Endpoint `ProfileParams` constrain placement/fleets/pricing; they do not change the preset's tested replica spec groups.
- `replica_spec_groups` order is part of the contract. If `service.replicas` is a list, `replica_spec_groups[i].name == service.replicas[i].name` for every group. If there is no replica-group list, the preset has exactly one implicit group (`"0"`), analogous to the default service replica group.
- Each replica group has one `resources` value used for offer matching and service submission. `tested_resources` may contain multiple exact entries, one per verified running replica. If the service needs different scheduling requirements, model those as separate replica groups.
- A preset has exactly one tested replica-spec topology. Hardware alternatives, benchmarked variants, and curated multi-choice registries are Later.

### 7.2 Interfaces

```python
class EndpointPreset(CoreModel):
    name: str                              # file stem
    model: str                             # matching key
    replica_spec_groups: list[EndpointPresetReplicaSpecGroup]  # ordered like service replica groups
    """Sorted to match `configuration.replica_groups`; group "0" is the implicit group."""
    configuration: ServiceConfiguration    # compiled service config, not the raw file

class EndpointPresetReplicaSpecGroup(CoreModel):
    """Ordered to match `ServiceConfiguration.replica_groups`; "0" is the implicit group."""
    name: str                              # replica group name; "0" for implicit group
    resources: ResourcesSpec               # scheduling requirements for each replica in the group
    tested_resources: list[ResourcesSpec]   # exact verified resources for running replicas

class EndpointPresetService(ABC):          # storage abstraction only — local dir first, S3/git later
    @abstractmethod
    async def list_presets(self, project_name: str) -> list[EndpointPreset]: ...

class LocalDirEndpointPresetService(EndpointPresetService):
    """Reads *.yml/*.yaml from settings.SERVER_PROJECTS_DIR_PATH / project_name / "presets".
    Re-reads per call; file IO via run_async.
    Invalid files are logged and skipped, never fatal."""

class EndpointPlanReplicaSpecGroup(CoreModel):
    name: str
    resources: ResourcesSpec
    tested_resources: list[ResourcesSpec]

class EndpointPlanJobOffers(CoreModel):
    replica_group: str
    offers: list[InstanceOfferWithAvailability]  # capped by max_offers
    total_offers: int
    max_price: Optional[float]

@dataclass(frozen=True)
class EndpointPresetPlan:                 # planning.py, not presets.py
    preset: EndpointPreset
    run_plan: RunPlan
```

Module-level `get_endpoint_preset_service()` returning the configured implementation (test-injectable).

### 7.3 Matching & submission

This is endpoint planning/orchestration logic, not `EndpointPresetService` storage logic.

`planning.py::find_matching_preset_plan(session, project, user, endpoint_name, endpoint_conf, preset_service=None) -> Optional[EndpointPresetPlan]`:
1. Candidates: presets whose top-level `model` equals `endpoint_conf.model` case-insensitively, in sorted file-name order. If there are no candidates, return `None` without refreshing the user's SSH key or calling the run planner.
2. For each candidate, build the merged service config (below), wrap in a `RunSpec` (repo fields `None` → virtual repo; `RunSpec.profile` is Optional), and call `runs.get_plan(session, project, user, run_spec, max_offers=1)`. Use the endpoint's effective `creation_policy`; if omitted, keep the normal run default `reuse-or-create` so elastic fleets may provision new instances. If the user explicitly sets `creation_policy: reuse`, matching becomes existing-instances-only. Match ⇔ every `job_plan` has ≥1 offer with `offer.availability.is_available()`.
   - Before plan/submission, mirror the run router's behavior: if the creator user has no `ssh_public_key`, call `users.refresh_ssh_key(...)` rather than failing the endpoint. This keeps endpoint apply consistent with `dstack apply` for services.
   - **Wrap each candidate in `try/except ServerClientError` → skip**: `get_plan` validates the merged config and can raise for a bad preset; one bad preset must not abort matching.
   - Cost note: the planner enumerates cloud backend offers per candidate cloud fleet (`plan.py::get_job_plans` → `find_optimal_fleet_with_offers`) — each candidate evaluation can take seconds. This is acceptable in `/get_plan` and the pipeline only because matching filters by model before planning and uses `max_offers=1`; keep the local preset set small and do not broaden matching into a registry scan in v1.
   - Known under-check, accepted for v1 (matching is advisory): `runs.get_plan` produces one representative `JobPlan` per replica group (`replica_num=0`), while the preset may record multiple tested resources per group. V1 verifies each group has at least one available matching offer for its `resources` and leaves full cardinality/capacity checks to the run scheduler. Capacity-aware matching over every tested replica is Later.
3. First match wins.

`EndpointPresetPlan` contains the selected `EndpointPreset` and the `RunPlan` computed from the merged `RunSpec`. The caller must submit that same plan/spec path rather than rebuilding independently, mirroring the run apply split between `runs.get_plan` and `runs.apply_plan`.

Merged service config (preset → endpoint overrides):
- start from the preset's compiled `ServiceConfiguration` (`service` plus resources derived from the ordered `replica_spec_groups` at the proper service/replica-group level);
- `name = get_endpoint_serving_run_name(endpoint.name)` (the backing service run name);
- merge `endpoint.env` **over** preset env (`Env.update`); endpoint env arrives fully resolved (sentinels rejected at create);
- copy every non-`None` `ProfileParams` field from `EndpointConfiguration` onto the service config (both inherit `ProfileParams`, so this is a field-loop like `RunSpec._merged_profile`, `core/models/runs.py:590-607`);
- do **not** merge or override resources from the endpoint: endpoints do not expose resources in v1, and the preset's replica group `resources` are the tested scheduling requirements;
- do not force `creation_policy = reuse`: the normal default `reuse-or-create` is intentional because existing dstack fleets may be elastic and allowed to provision new instances for submitted services/jobs.

How this runs without the agent: the local preset loader injects `replica_spec_groups[0].resources` into top-level `service.resources` for the implicit group, or injects `replica_spec_groups[i].resources` into `service.replicas[i].resources` for explicit replica groups. It also leaves `service.replicas`/`scaling` intact, so the normal service planner/submission path decides how many replicas to start and where to place them. `len(replica_spec_groups[i].tested_resources)` records the verified running replica count at save time; it is evidence and future inspect/JSON input, not a replacement for service `replicas`/autoscaling.

Submission: `RunSpec(run_name=get_endpoint_serving_run_name(endpoint.name), configuration=merged, ssh_key_pub=None)` as the creator user, using the same policy/SSH-key behavior as the run router (`refresh_ssh_key` if needed; do not let `get_plan` and the final run submission see different specs). If validation still fails, surface that as endpoint FAILED.

Fleet-drift note: matching is advisory — a fleet can become busy between match and provisioning. No hard endpoint→fleet binding.

### 7.4 Saving agent-proven presets (v1)

When an agent-created backing service becomes `RUNNING` through the normal service readiness path, save a sanitized `endpoint-preset` wrapper back into the endpoint project's local preset directory (`<server dir>/projects/<project name>/presets`). This makes the second endpoint for the same model in the same project take the deterministic preset path instead of paying the agent again.

Implementation details:
- Extend `EndpointPresetService` with project-scoped operations such as `save_preset(project_name, preset, comments) -> EndpointPreset`. The local implementation writes a `type: endpoint-preset` YAML file under `settings.SERVER_PROJECTS_DIR_PATH / project_name / "presets"` using an atomic temp-file rename. File names should be stable and collision-resistant, e.g. `<slugified-model>-<short-run-id>.dstack.yml`; do not overwrite hand-authored presets.
- Source of truth is the backing run's stored `RunSpec.configuration` plus the latest successful job submissions after the service has reached `RUNNING`, not the agent's final text. Sanitize before writing: top-level `model` comes from the verified service model; `replica_spec_groups[*].resources` is copied from the verified service configuration's per-group scheduling requirements; `replica_spec_groups[*].tested_resources` are built from jobs grouped by `JobSpec.replica_group` in `ServiceConfiguration.replica_groups` order, deriving each exact instance `ResourcesSpec` from `JobRuntimeData.offer` when present or the backing `InstanceModel.offer` as fallback. The `service` section preserves the serving recipe/shape fields (`image`, `commands`, `port`, `model`, `volumes`, `replicas`, probes, scaling) but clears `type`, `name`, all resource fields, and `ProfileParams`. Merge env as names only for endpoint-provided keys and redact secret-looking values (`TOKEN`, `KEY`, `SECRET`, `PASSWORD`) to name-only entries. Never write resolved secret values from `EndpointConfiguration.env` to disk.
- Preserve provenance as YAML comments at the top (comments do not affect preset parsing): endpoint name/id, run id, dstack version, timestamp, agent model, job ids that produced the replica spec groups, and recipe source URLs from the agent's structured final report. Do not add a metadata object in v1.
- Failure to save the preset logs a warning and emits an event, but it does **not** fail an already-running endpoint. Tests should cover successful write, duplicate-name avoidance, invalid destination permissions, and secret redaction.

---

## 8. Agent subsystem

`src/dstack/_internal/server/services/endpoints/agent/`.

**Current planning note:** this section has been reset to the CLI-first Path B: the agent uses the real `dstack` CLI in a bounded workspace and performs final functional verification. The server owns endpoint state, run linking, service-readiness bookkeeping, and preset saving; it must not treat its own readiness checks as proof that the requested model works.

### 8.1 Abstraction

```python
@dataclass(frozen=True)
class AgentProvisioningResult:
    run_id: Optional[uuid.UUID] = None
    run_name: Optional[str] = None
    error: Optional[str] = None

class AgentService(ABC):
    @abstractmethod
    def is_enabled(self) -> bool: ...
    @abstractmethod
    def get_plan(self) -> AgentPlan: ...
    @abstractmethod
    async def provision_endpoint(
        self,
        endpoint_model: EndpointModel,
        pipeline_hinter: PipelineHinterProtocol,
    ) -> AgentProvisioningResult: ...
```

`get_agent_service()` returns the real Claude agent service when enabled, else a disabled stub. Fully injectable for tests (pytest runs with `--disable-socket`; nothing in the test suite may touch the live agent runtime or external APIs). The pipeline requires a successful agent verification report plus the backing `run_id`/`run_name` or an error. Provenance details flow to preset saving/logging only after the server also confirms normal service readiness.

### 8.2 `ClaudeAgentService` — real agent runtime

**v1 must use a real Claude agent runtime, not a raw LLM API loop.** The previous raw `anthropic` Messages prototype was removed because it recreated a primitive tool loop instead of giving the agent a real shell/filesystem/code workflow. The current v0 implementation invokes the Claude Code executable as a subprocess from an endpoint workspace. If Claude Code proves unsuitable after live runs, choose another real agent runtime; only fall back to building a custom loop after an explicit design review.

What this means for v1:
- *Runtime hardening through live runs*: keep the Claude Code subprocess path intentionally simple, then harden it based on real endpoint attempts. It must operate non-interactively, use the real `dstack` CLI, create/edit files, inspect logs/status, preserve artifacts, emit a final machine-readable report, avoid duplicate live agent processes after restarts, and support endpoint stop aborts.
- *CLI-first dstack operations*: planning, submission, status inspection, log reading, and stopping are done through the same `dstack` CLI a user would run: `dstack apply`, `dstack ps`, `dstack run get --json`, `dstack logs`, and `dstack stop`. Do not build duplicate custom tools named `submit_service`, `get_run_status`, `get_run_logs`, etc.
- *Termination contract*: the agent returns a structured final report with success/failure, final candidate run name/id, final service YAML/content, recipe sources, and verification summary. The agent is responsible for final functional verification. The server does not trust the report blindly; it validates the claimed run identity and project/user ownership before linking the run, then waits for normal dstack service readiness before activating the endpoint. The readiness gate is bookkeeping, not a server-side claim that the model works.
- *Environment hygiene*: the agent runtime receives only the credentials it needs to authenticate to Claude plus the isolated dstack CLI config for the target project. The command/workspace environment remains scrubbed: do not expose server DB credentials, encryption keys, cloud backend credentials, or unrelated server env vars.
- *Abortability*: endpoint stop must be able to stop or ask the agent runtime to stop. This is not complete in the v0 subprocess runtime yet: the worker can hold the endpoint lease while Claude runs, and stop-time cancellation/restart-safe recovery must be hardened before production use.

Packaging requirement: agent runtime dependencies must be installed automatically by normal server deployment paths. The server runtime must not depend on `uv` being available. The Claude Agent SDK currently depends on pydantic v2 while dstack still runs pydantic v1, so v0 invokes the Claude Code executable directly instead of importing the SDK into the server process. Docker release and staging images copy the bundled Claude Code binary into `/usr/local/bin/claude` at build time. `DSTACK_AGENT_CLAUDE_PATH` may point the server at a specific Claude Code executable; when it is unset, `ClaudeAgentService` resolves `claude` from `PATH`. For non-Docker installs, automatic non-Docker packaging for that executable remains a release-blocking follow-up before the agent path can be considered production-ready.

Packaging gate before enabling `ClaudeAgentService`:
- The server process stays dependency-compatible with pydantic v1 and does not require `uv` at runtime.
- Server Docker release and staging images include the Claude Code executable without an operator shelling into the container to install it manually.
- The availability check used by `get_agent_service()` validates the API key and required `claude` executable, and reports a clear server-install problem if packaging regresses.
- Tests or CI checks cover at least the Python dependency metadata and runtime availability probe; Docker verification is part of the manual e2e runbook if it is too heavy for unit CI.

### 8.3 CLI-first harness

The important product work is the harness, not the HTTP loop. The agent should behave like a careful dstack developer using the CLI, with strong context and boundaries:
1. understand the requested model and endpoint constraints;
2. gather grounded recipe + hardware evidence from credible sources;
3. inspect the project context and available fleet/offer envelope through CLI/status output;
4. draft the smallest service YAML that should work;
5. preview with `dstack apply -f <service.yml>` before spending GPU time;
6. submit detached with `dstack apply -f <service.yml> -y -d` only when the plan is acceptable within the endpoint/profile/budget envelope;
7. debug with `dstack ps`, `dstack run get <run> --json`, and `dstack logs`;
8. stop bad candidates with `dstack stop <run> -y` and let normal run lifecycle handle termination/deletion;
9. finish only after the final service is RUNNING, has a registered replica, exposes a model URL, and the agent has made a final model request proving the requested model is actually served.

This is intentionally **not** a new server-side mini API for dstack. The harness should provide:
- an endpoint-scoped working directory for service YAMLs, notes, and command transcripts;
- the real `dstack` binary from the running installation;
- a CLI config/context that targets the correct server, project, and endpoint creator user;
- endpoint constraints: model, env names, ProfileParams, preset policy, and allowed resource/spend envelope;
- recipe grounding guidance and optionally preloaded recipe/context snippets, not a required `find_model_recipes` tool;
- command logging and a `should_abort()` check between command iterations so deletion can interrupt long agent work;
- a structured final-report schema.

The preset path uses a server-owned deterministic run name from `get_endpoint_serving_run_name(endpoint.name)` because the server submits that service itself. The agent path does not force that naming convention. Claude may choose concise, unique candidate and final run names; the server validates and links the final service by reported run ID, then records it in `EndpointModel.service_run_id` and `EndpointRunSubmissionModel`.

Dev-environment and task prototyping are allowed in the v0 agent prompt when they are the fastest way to reduce uncertainty about an image, launch command, model download, or hardware choice. For v1, advanced P/D disaggregation, multi-service routers/workers, load benchmarking, and autoscaling tuning are Later unless needed to make the requested model serve at all.

### 8.4 Prompt, recipe grounding & vendored context

Runtime context layout:

- `resources/system_prompt.md` — endpoint-specific mission and protocol only: use the real CLI, load `/dstack` and `/dstack-prototyping`, honor endpoint constraints, emit concise progress events, verify the final model API request, and return the structured final report.
- repo-root `skills/dstack/SKILL.md` — CLI/config source of truth.
- repo-root `skills/dstack-prototyping/SKILL.md` — reusable research-to-working-workload skill: source order, model-serving recipe selection, hardware fit, dev-environment/task/service experiment choice, failure classification, final service cleanup, and model API verification.

`pyproject.toml` force-includes repo-root `skills/**` into wheels/sdists. The workspace setup locates that packaged `skills` directory and copies only `dstack` and `dstack-prototyping` into `.claude/skills` for each endpoint-agent run. The prompt explicitly names `/dstack` and `/dstack-prototyping`; do not rely on an operator's user-level Claude/Codex skills.

`dstack-prototyping` should answer both "how do I experiment on dstack?" and "what should I try deploying for this model/framework/hardware?" It must stay generic to dstack workload prototyping and must not mention endpoint statuses, preset saving, endpoint DB rows, or Claude-specific implementation details. Endpoint-specific requirements stay in `system_prompt.md`.

Recipe grounding should be source-oriented, not a static recipe encyclopedia. The agent should prefer current primary sources such as model cards, vLLM/SGLang docs, dstack docs/CLI help, and its own command/log evidence. Advanced posts such as Wafer GLM-on-AMD and LMSYS agent-assisted SGLang development are directional for future harness work, not v1 requirements.

The prompt interpolates endpoint env keys (names only), ProfileParams constraints, project context, and effective agent budget. Recipe grounding is discovered by the agent through allowed network/command facilities and recorded in the final report; do not model it as a required `find_model_recipes` function in v1.

### 8.5 Execution, cost & limits

- Runs inside the pipeline worker (§6.2) unless the chosen runtime forces a detached process model. Agent execution must not block the event loop; use async subprocess/process supervision or a small dedicated executor with bounded concurrency, not the shared 128-thread default executor.
- Between agent/runtime steps, or through runtime cancellation hooks, the service checks `should_abort()` (cheap SELECT of stop intent + `lock_token` sanity) and exits early on stop.
- Do **not** add generic endpoint provisioning timeouts or unused turn/attempt counters. The real agent loop should introduce budgets only where they are enforced. v0 uses the endpoint configuration's `max_agent_budget` value, falling back to `DSTACK_AGENT_ANTHROPIC_MAX_BUDGET_USD`, and passes the effective value to Claude Code's `--max-budget-usd` as the hard per-agent-process cost cap. Once retries/resumes or multiple Claude processes per endpoint provisioning are added, dstack must persist and sum agent spend per endpoint provisioning attempt before starting the next process, so the total endpoint provisioning budget cannot be bypassed by restarts.
- Model via `DSTACK_AGENT_ANTHROPIC_MODEL` if the selected runtime supports explicit model selection (default: `claude-opus-4-8`; the default agent should bias toward the strongest Anthropic model because endpoint provisioning is an expensive, tool-heavy deployment investigation).
- Concurrency bound = pipeline `workers_num` per replica (4).
- Observability: log each command + final summary at INFO with the endpoint id; store command transcripts under the endpoint workspace or log service for debugging; store the final agent summary in `status_message` on failure; log provider usage for token-budget accounting; store `recipe_sources` in the saved preset comments on success. Cost accounting/events → Later.

---

## 9. Settings, packaging, docs

New in `src/dstack/_internal/server/settings.py` (documented in `mkdocs/docs/reference/env.md`, as the module docstring requires):

| env var | constant | default | notes |
|---|---|---|---|
| `DSTACK_AGENT_ANTHROPIC_API_KEY` | `AGENT_ANTHROPIC_API_KEY` | `None` | as specified by the requirement (agent-scoped, hence no `_SERVER_`); presence ⇒ agent enabled |
| `DSTACK_AGENT_CLAUDE_PATH` | `AGENT_CLAUDE_PATH` | `None` | optional path to the Claude Code executable; falls back to resolving `claude` from `PATH` |
| `DSTACK_AGENT_ANTHROPIC_MODEL` | `AGENT_ANTHROPIC_MODEL` | `claude-opus-4-8` | override only if the operator intentionally wants a cheaper/faster model |
| `DSTACK_AGENT_ANTHROPIC_MAX_BUDGET_USD` | `AGENT_ANTHROPIC_MAX_BUDGET` | `None` | optional server default for endpoint agent spend; overridden by endpoint `max_agent_budget`; future retry/resume support must sum spend across processes per endpoint provisioning attempt |

Plain module constants in `settings.py`, not env-configurable in v1: `SERVER_PROJECTS_DIR_PATH = <server dir>/projects`, `ENDPOINT_RUNNING_CHECK_INTERVAL = 60s`.

Packaging: the selected real agent runtime dependency/binary is installed automatically without contaminating the server Python environment and without requiring `uv` at runtime. For Docker this means copying the bundled Claude Code executable into the image at build time. For non-Docker server installs, automatic packaging of the `claude` executable must be solved before the agent path is production-ready. Treat this as a release blocker for enabling the Claude agent path, not as optional docs.

Docs: `mkdocs/docs/reference/dstack.yml/endpoint.md` with `#SCHEMA# dstack._internal.core.models.endpoints.EndpointConfiguration` (processed by `scripts/docs/gen_schema_reference.py`), added to `mkdocs.yml` nav and the `reference/dstack.yml.md` index; env vars in `reference/env.md`; a short concepts page ("Endpoints — experimental") once the feature works end-to-end.

---

## 10. Implementation milestones (each ≈ one PR)

**M1 — resource skeleton (no processing).** `core/models/endpoints.py` + registration in `configurations.py`; `EndpointModel` + migration + events wiring; `EndpointPlan` models with the `none` provisioning branch; `services/endpoints/__init__.py` (create/stop/list/get/get_plan shell, status switch, events); schemas + router + `app.py`; `_endpoints.py` API client group; CLI configurator + `EndpointCommand`. Endpoints can be planned/created and sit SUBMITTED forever. Tests: router CRUD, name uniqueness/reapply semantics, configurator parse, sentinel rejection, plan output for no preset/no agent.
**M2 — pipeline & lifecycle.** `background/pipeline_tasks/endpoints.py` + registration; the full state machine of §6.2 with `AgentService`/`EndpointPresetService` as interfaces with disabled/empty defaults (so: SUBMITTED→FAILED "nothing configured", preset-path run-name conflict detection, RUNNING backing-run liveness through `service_run_id`, simple two-phase server-side stop of the linked service run, and FAILED teardown rule). Tests: fetcher query (sqlite+postgres, lock claims, RUNNING cadence, STOPPING handling), every worker transition with fakes, conflict detection, linked-run cleanup. Do not test name-based adoption as ownership.
**M3 — presets + plan offers.** `presets.py` (`EndpointPresetService`, `LocalDirEndpointPresetService`, project-scoped storage/parsing only under `<server dir>/projects/<project name>/presets`), `endpoint-preset` wrapper parsing (`service` recipe + ordered tested `replica_spec_groups`), `planning.py` matching via `get_plan` using the endpoint's effective `creation_policy` (default `reuse-or-create`, so elastic fleets are allowed), per-candidate `ServerClientError`/unresolved-env skip, config merge, submission path, `EndpointPlan.provisioning_plan=type:"preset"` only for provisionable presets with tested replica spec groups and offer summary, save-preset interface + sanitizer. Tests: matching unit tests with testing factories (project/fleet/instance), project isolation, merge semantics, invalid preset files skipped, bad-preset-skip, no-offer preset falls through to agent when policy allows, plan prints selected preset/offers/replica spec groups, secret redaction, atomic write/no-overwrite.
**M4 — agent + endpoint logs.** Build on `service_run_id` + `EndpointRunSubmissionModel` so only the latest run serves while submission history is preserved. Continue hardening `ClaudeAgentService` around the v0 Claude Code subprocess runtime: workspace/process handling, scrubbed environment, structured final report artifact, vendored context, `EndpointPlan.provisioning_plan=type:"agent"`, agent settings, automatically installed runtime dependencies, `should_abort`/process cancellation, successful-agent preset save on `RUNNING`, `dstack endpoint logs`, and non-detached endpoint apply following server-side logs/status without attach. Tests should cover real runtime integration boundaries actually used by `ClaudeAgentService`, final-report parsing, runtime availability packaging checks for the `server`/`all` extras, endpoint logs command behavior, apply does not call attach, fake-runtime service integration, and FakeAgentService pipeline integration; mocked network/CLI where possible. Manual e2e: local `uv` server install plus server Docker image both reach the same runtime availability state with only `DSTACK_AGENT_ANTHROPIC_API_KEY` configured.
**M5 — docs & polish.** Reference page, env.md, concepts page, `dstack endpoint` help texts, endpoint plan rendering polish, example presets in docs (not shipped as defaults — §11 Q7), manual e2e runbook (local server + real fleet + one preset + one agent deploy).

---

## 11. Key open questions — with recommended answers

1. **Run naming & history.** Q: how to link endpoint↔run and what happens on retries? **A:** preset-backed services use `<endpoint>-serving` when valid because the server submits them. Agent-backed services are linked by reported `run_id`; the agent chooses concise unique run names. `service_run_id` is authoritative for the serving run; name lookup is conflict detection only for preset submission. `EndpointRunSubmissionModel(endpoint_id, run_id, submission_num, submitted_at)` records endpoint-submitted run history without coupling `RunModel` to endpoints. Agent retry policy → Later.
2. **Who owns the backing run?** Q: which UserModel submits it (no system user exists)? **A:** the endpoint's creator (`user_id` on the row) — correct attribution in events/quotas; mirror the run router by refreshing the user's server-managed SSH key before `get_plan`/submission if missing. A first-class service account → Later.
3. **Where does the agent execute?** Q: inside the pipeline worker vs a detached task with its own heartbeat bookkeeping? **A:** v0 runs inside the worker `process()` under the Heartbeater lease, with `workers_num=4` as the concurrency bound. This is enough to test the real loop, but stop-time cancellation and restart-safe recovery are not done: `stop_endpoints` can mark the endpoint `STOPPING` without acquiring the lock, but the live Claude subprocess still needs an explicit abort/supervision path.
4. **Which Claude runtime?** **A: v0 uses Claude Code headless/subprocess after rejecting the raw `anthropic` Messages loop.** Continue validating non-interactive server execution, cancellation, workspace/env isolation, final artifact extraction, restart behavior, and packaging. If Claude Code proves unsuitable after real deployments, choose another real agent runtime before adding more harness complexity.
5. **Permissions.** Q: `ProjectMember` (volumes) or `ProjectAdmin` (gateways)? **A:** `ProjectMember` — endpoints are project workloads that consume the same quota surface as runs, not shared admin infrastructure.
6. **Preset match semantics.** Q: what does "matches the existing fleets" mean concretely? **A:** A model-matched preset is only **provisionable** when `get_plan` on the merged config returns ≥1 available offer for every job plan using the endpoint's effective `creation_policy`. Default `reuse-or-create` may return offers from elastic fleets that can create new instances; explicit `reuse` restricts to currently existing instances. Only provisionable presets are submitted automatically. If presets match the model but no offers are available, `preset_policy: reuse` stops with no-offers/no-fleets, while `reuse-or-create` falls through to the agent path if available. Advisory, not a binding; known to under-check multi-replica capacity (§7.3), accepted for v1.
7. **Do we ship built-in presets?** **A:** No — empty preset dir by default; docs show copy-paste presets, and successful agent deployments write local learned presets. Shipping curated presets with the wheel makes dstack responsible for third-party image/version rot on every release; revisit with a versioned preset registry (Later).
8. **Feature flag?** **A:** No `DSTACK_FF_*` flag. The feature is inert unless a preset dir is populated or the agent key is set; a config-type flag would have to gate client-side parsing too, which FFs here don't do. Document as experimental.
9. **Env var naming.** **A:** keep `DSTACK_AGENT_ANTHROPIC_API_KEY` exactly as specified (breaks the `DSTACK_SERVER_*` convention deliberately: it namespaces a future family of `DSTACK_AGENT_*` settings).
10. **Plan/apply surface.** **A:** v1 ships an advisory `get_plan` plus create/stop/list/get/logs/preset. `dstack apply` always shows the endpoint plan before confirmation, but submit remains create-and-background-process; no endpoint `apply_plan` or in-place update until Later.
11. **Endpoint updates.** **A:** stop/override only in v1. Later in-place endpoint updates must reuse existing service-run `get_plan`/`apply_plan` and rolling deployment (`deployment_num`, desired replica counts, service registration/probes). Endpoint DB updates need their own `configuration_version`/deployment guard so a stale worker in a multi-server Postgres deployment cannot mark a newer endpoint config running.

---

## 12. Later (explicitly deferred)

Carried over from the requirements ("later we…") plus deferrals made above:

- **Preset sources beyond local dir**: S3, git repo (reuse the `services/templates.py` clone/TTL machinery), HTTP registry; richer provenance metadata (version pins, observed offer, benchmark results), signed/curated preset channels; shipping default presets; capacity-aware matching over every recorded replica spec and exact offer identity.
- **Preset update policy**: allow the agent to update/replace an existing learned preset only as a repair path, not as optimization. The harness must first prove that the old preset is not reproducible under the conditions it claimed to support (for example same model family/recipe constraints and compatible tested resource topology, but repeated normal preset-path attempts fail for reasons attributable to the preset rather than transient capacity/no-offers/user constraints). Only then may it save a replacement or new version, with evidence of the failed reproducibility attempt and the newly verified deployment. V1 learned presets stay append-only/no-overwrite until this policy is designed and tested on real failures.
- **Automatic provisioning retry policy**: retry failed provisioning through SUBMITTED, backoff, retry history retention, and distinct candidate run names if preserving failed candidates becomes important.
- **Agent retry policy for RUNNING endpoints**: instead of FAILED on health-check failure, re-invoke the agent to diagnose/redeploy; backoff policy; `retry` ProfileParams semantics for endpoints.
- **Alternative agent runtime** — revisit if the first real runtime cannot meet server requirements for non-interactive execution, packaging, cancellation, workspace/env isolation, artifact capture, and cost accounting.
- **Other `AgentService` implementations** (OpenAI-compatible, Bedrock/Vertex via the SDK's provider clients, self-hosted).
- **Richer service creation**: deepen `dstack-prototyping` through real endpoint-agent traces; richer attach/SSH automation for dev environments; benchmarking before marking an endpoint running; autoscaling/replicas/gateway/domain decisions; quantization variant selection; multi-node deployments; P/D disaggregation and other multi-component serving topologies; advanced SGLang development/deployment harnesses inspired by the 2026-07-02 LMSYS agent-assisted SGLang workflow.
- **Workload-aware optimization**: benchmark and tune endpoints by workload profile (chatbot, RAG, code generation, long-form generation), measuring TTFT, ITL, throughput, end-to-end latency, quality, and cost/token. Product references such as Modal Auto Endpoints, Makora, and Runpod Overdrive are useful directionally, but v1 must stop at verified functional deployment and reproducible preset provenance.
- **In-place update / plan-apply**: server-side endpoint `get_plan`/`apply_plan`, model or config changes via the existing service-run `apply_plan` + rolling deployment machinery, no stop/recreate for simple changes; endpoint row updates protected by a `configuration_version`/deployment guard for multi-server safety.
- **Deletion escalation**: forced abort / operator-facing stuck-deletion handling if a backing run remains terminating beyond the normal RunPipeline retry window.
- **Plugins**: add an `EndpointSpec` to the `ApplySpec` TypeVar (`dstack/plugins/_models.py:8`) so plugin policies can reason about endpoint-level intent directly. Backing service runs still use normal run policies in v1.
- **Frontend UI**: endpoints page in the server frontend. No frontend work is required in v1.
- **Richer progress surfaces**: agent transcript/event streaming beyond concise status/log-following; structured display of recipe evidence and harness decisions in CLI/UI.
- **Cost & governance**: per-project agent budgets, token/cost accounting per endpoint, API key via the encrypted secrets service (`services/secrets.py`) instead of a server-wide env var, audit events for every agent tool call.
- **Agent hardening**: policy hooks on tool calls, sandboxed execution, structured-output enforcement of the final report beyond the `finish` tool.
- **Vendored recipe snapshots** for air-gapped servers (Apache-2.0 attribution), refresh tooling.
- **Model catalog UX**: `dstack endpoint models` listing known-deployable models from presets + recipes indexes.

---

## 13. Risks & mitigations (summary)

| risk | mitigation in this plan |
|---|---|
| Replica death mid-agent-run duplicates deployments / spend | `service_run_id` points to the latest run and `EndpointRunSubmissionModel` records accepted endpoint-submitted runs. The heartbeater lease prevents duplicate live workers while the replica lives; after a crash, the next worker reconciles by linked run/submission history. Name lookup is conflict-only (§6.2, 6.3, 6.5) |
| Paid crash loop (pipeline re-fetch + flaky agent) | no automatic retry in v1 + terminal FAILED stops re-fetching; real agent loop must add explicit token/cost/wall-clock budgets before it can spend on experiments |
| Adopting/destroying an unrelated user run with the same name | name lookup is conflict detection only; ownership must come from `service_run_id` or `EndpointRunSubmissionModel` rows, never from name/user/timestamp heuristics (§6.5) |
| One-shot stop+delete of runs always raising | endpoint stop remains two-phase stop → wait-until-finished → stopped. The CLI-agent should use normal `dstack stop <run> -y` for bad candidates and let run lifecycle handle termination (§2.5, §8.3) |
| GPU-run leaks on terminal FAILED | every FAILED transition issues `stop_runs` for a still non-terminal backing run (§6.2) |
| Transaction/lock corruption submitting backing runs from the worker | fresh `get_session_ctx()` for all runs-service calls; endpoint row writes stay token-guarded; any interim progress update leaves lock columns untouched (§6.1) |
| Prompt injection via fetched recipes → server compromise | command execution runs in an endpoint-scoped workspace with a scrubbed environment; the agent uses normal `dstack` CLI rather than server internals; server secrets/DB/cloud credentials and the agent API key are not exposed to commands (§8.2, 8.3) |
| Agent-learned preset writes resolved secrets to disk | preset sanitizer clears `name`, writes endpoint env as names only, redacts secret-looking values, and tests secret redaction (§7.4) |
| Event-loop starvation from long agent IO | supervise the agent runtime with async subprocess/process APIs or a bounded dedicated executor; never the shared default executor; small `workers_num` |
| `RunStatus.RUNNING` ≠ model ready | endpoint `RUNNING` requires a registered running service replica and `ServiceSpec.model.base_url`; endpoint v1 does not add a parallel health probe (§6.4) |
| `MissingGreenlet` on lazy `project.backends` in the worker | refetch joinedloads chain `project → backends` (§6.1) |
| `register_service` raises synchronously during backing run submission (gateway config issues) | caught as submission failure ⇒ FAILED with message; agent prompt includes gateway context |
| Agent deploys a service without `model:` → no model URL to surface | prompt requires `model:`; agent final verification must use the model endpoint, and server readiness validation refuses to mark the endpoint running unless the backing service exposes `ServiceSpec.model.base_url` (§6.2, §8.3) |
| Preset/fleet drift between match and provisioning | matching is advisory; run scheduling is source of truth |
| Agent runtime dependency missing in deployment | selected runtime dependencies are included in normal server install paths and Docker images; release Docker uses `dstack[all]`, staging uses `uv sync --extra all`, and local server installs must not require manual runtime installation (§8.2, 9) |
| Missing migration passes unit tests silently | migration is an explicit M1 review item; postgres-parametrized tests |
