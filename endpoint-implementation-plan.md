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
- Each preset is keyed by model and contains one or more deployment recipes. A recipe's `service` contains the scheduling resources used for reuse/offer matching; `validations` store exact verified hardware evidence grouped in the same order as the service replica groups.
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
- [x] Preset storage/parsing: `EndpointPresetService`, project-local implementation under `<server dir>/projects/<project>/presets`, `endpoint-preset` YAML wrapper, model-keyed `recipes`, ordered `validations`, legacy `replica_spec_groups` conversion, validation, merge-by-model list/get/save/delete, env value redaction, and literal non-secret env preservation.
- [x] Learned preset plumbing: build or merge a model-level preset from a ready service run, preserve the service recipe/resources as the scheduling contract, record exact running replica resources in `validations`, and save it when an agent-provisioned endpoint becomes running.
- [x] Endpoint preset CLI: `dstack endpoint preset list|get --json|delete`. The compact list groups by model and shows only the scheduling GPU; `-v` shows full service scheduling resources. Child `recipe=N` rows appear only when a model has multiple recipes; internal recipe ids and exact verified hardware stay in `get --json`.
- [x] Endpoint list UX now follows the `ps` convention more closely: default output shows unfinished endpoints, or the latest finished endpoint only when nothing is active; `POLICY` is shown by default and the backing service run is only shown in verbose/detail/JSON output.
- [x] Endpoint status names adjusted: `prototyping` while the server agent investigates/deploys, `running` for a ready endpoint, `stopping`/`stopped` for endpoint stop. The runtime `active` alias was removed; local prototype DB rows should be cleaned directly.
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
- [x] Fresh create-policy Claude run: `Qwen/Qwen2.5-0.5B-Instruct` on RunPod reached `running`, verified a real OpenAI-compatible chat request, saved preset `qwen-qwen2-5-0-5b-instruct-e30ddb94`, and stopped the backing run cleanly.
- [x] No-cost reuse preview for the fresh Qwen2.5 preset selected the learned preset and found 5 matching RunPod offers under the endpoint constraints.
- [x] Paid reuse deployment for the fresh Qwen2.5 preset reached `running` without Claude, answered a model request on RunPod A5000, and stopped cleanly.
- [x] Fresh create-policy rerun after prompt/env fixes exposed a real harness weakness: the agent stopped using `~/.dstack/config.yml` and append-only submission records worked, but it repeatedly submitted full services on a container backend to learn runtime facts that should be prototyped with a dev environment or small task when an allowed reusable VM/SSH fleet exists.
- [x] Stop-time agent cancellation implemented after the live leak: `dstack endpoint stop` now asks the agent runtime to abort, terminates the stored Claude process group, keeps the endpoint `stopping` if the agent process is on another host, and still stops linked/submitted runs through `EndpointRunSubmissionModel`.
- [x] Stop-time cancellation live validation: stopping before Claude starts and stopping after Claude starts both reached `stopped` with no endpoint-submitted runs left. A zombie-only process-group issue was found and fixed during validation.
- [x] Historical create-policy run in an isolated project with no fleets proved the real agent loop could deploy and verify a model, but also showed an unwanted contract: Claude created an endpoint-scoped fleet. That behavior is now rejected; fleet creation is a user/admin step before endpoint submission.
- [x] No-fleet contract validation: with no active fleet, endpoint apply now shows "The project has no fleets. Create one before submitting an endpoint." for any `preset_policy`; forced detached apply exits `1` and does not resubmit a terminal endpoint. The pipeline also fails already-submitted endpoints with the same no-fleets status before preset or Claude processing.
- [x] Existing-fleet contract validation: after creating zero-target fleet `endpoint-agent-reasoning-fleet`, the endpoint plan returned the agent path. Claude started, inspected the existing fleet, correctly ignored prior stopped run `qwen25-7b-vm-reasoning-1` as old/different-fleet work, and used `dstack offer --fleet endpoint-agent-reasoning-fleet ...`. The run was stopped before any new service submission or GPU spend.
- [x] Endpoint progress stream no longer prescribes labels/categories/templates: the server accepts plain text progress lines or JSON objects with a `message` string and displays only the message text.
- [x] Harder existing-fleet e2e exposed prompt-only enforcement failure: Claude correctly used `dstack offer --fleet endpoint-agent-reasoning-fleet`, then wrote a probe task without `fleets` and submitted it. The task failed with `no offers` before provisioning (`cost: 0.0`), and the endpoint/agent were stopped. A workspace-local `dstack` CLI guard now blocks fleet apply and blocks agent-submitted run configs that omit or violate explicit endpoint `fleets`.
- [x] Harder existing-fleet e2e after the CLI guard succeeded end-to-end: `Qwen/Qwen2.5-7B-Instruct` deployed on existing fleet `endpoint-agent-reasoning-fleet`, selected Jarvis L4:24GB at `$0.44/hr`, served through `vllm/vllm-openai:v0.24.0`, answered a real `/v1/chat/completions` request, saved project preset `qwen-qwen2-5-7b-instruct-d79aa1d8`, and stopped cleanly. The test fleet was deleted afterward to stop idle spend.
- [x] Guard behavior validated in the live run: Claude first wrote a service config without `fleets`, the workspace-local `dstack` shim rejected it, Claude corrected the YAML to include `fleets: [endpoint-agent-reasoning-fleet]`, previewed/applied it, and the final saved preset remained usable without Claude.
- [x] Learned-preset reuse preview validated for the 7B run: while the original service occupied the only `nodes: 0..1` fleet slot, reuse correctly matched the preset but showed no offers; after stopping the endpoint, the same preview selected the preset and showed the idle Jarvis L4 offer without invoking Claude.
- [x] Agent CLI guard now enforces the default "all existing project/imported fleets" path by passing discovered active usable fleet names into the workspace shim, and rejects `dstack offer` / `dstack apply` calls that omit allowed fleets or violate accepted endpoint profile constraints such as backend, region, instance type, spot policy, max price, durations, instances, tags, and backend options.
- [x] Fresh RunPod existing-fleet e2e after the guard: `Qwen/Qwen2.5-1.5B-Instruct` with `preset_policy: create`, `backends: [runpod]`, `fleets: [endpoint-e2e-runpod]`, `spot_policy: on-demand`, and `max_price: 0.5` reached `running`. Claude first omitted `fleets` in the service YAML, the workspace shim rejected the preview, Claude corrected the config, the first service submission failed with transient RunPod `failed_to_start_due_to_no_capacity`, the second submission added retry, landed RTX 2000 Ada at `$0.24/hr`, answered `/v1/chat/completions`, saved preset `qwen-qwen2-5-1-5b-instruct-4d68b0a3`, and `dstack endpoint stop` terminated the backing run cleanly.
- [x] Immediate reuse preview for that saved Qwen2.5-1.5B preset validated both capacity states: while the only allowed RunPod fleet slot was occupied, the plan selected the preset but showed no offers; after stopping the endpoint, the same reuse preview selected the preset and showed 7 matching offers without invoking Claude.
- [x] Prompt/skill tightened from the fresh trace: final service YAML must carry applicable endpoint constraints, progress must report run-capacity/running/final-verification milestones, polling/probe commands must stay bounded to avoid Claude Code Bash timeouts, and `final_report.json` must stay limited to the JSON-schema fields while hardware/driver/reasoning evidence lives in workspace artifacts.
- [x] Fresh validation run after prompt/skill tightening: `Qwen/Qwen2-0.5B-Instruct` with `preset_policy: create`, `backends: [runpod]`, `fleets: [endpoint-e2e-runpod]`, `spot_policy: on-demand`, and `max_price: 0.5` reached `running`, answered `/v1/chat/completions`, saved preset `qwen-qwen2-0-5b-instruct-532ddf05`, and stopped cleanly. Improvements were real: the first service YAML included `fleets`, endpoint logs included running and verification milestones, polling was bounded instead of concurrent watchers, and `final_report.json` was schema-clean. Remaining harness/preset quality issues from the same trace: the service requested `gpu: 1` without a GPU-memory floor, wrote a transient `"run_id":"pending"` submission record, waited on a Uvicorn log marker after an early proxy probe, and still did not capture a direct `nvidia-smi` driver string.
- [x] Immediate reuse preview for the saved Qwen2-0.5B preset validated both capacity states: while the only allowed RunPod fleet slot was occupied, the plan selected the preset but showed no offers; after stopping the endpoint, the same reuse preview selected the preset and showed 7 matching offers without invoking Claude.
- [x] Removed the premature agent-budget surface from v1: no endpoint `max_agent_budget`, no `DSTACK_AGENT_ANTHROPIC_MAX_BUDGET_USD`, no DB/session spend fields, no CLI plan row, no API plan `max_budget`. Cost/budget governance is Later and must be added only with durable per-session accounting.
- [x] Tightened the endpoint system prompt and `dstack-prototyping` skill after the `gpu: 1` trace: final LLM services should normally request a defensible GPU memory/count envelope, and count-only GPU scheduling must be intentional and recorded in hardware reasoning.
- [x] Agent session restart semantics tightened: a server restart or dead same-host Claude process resumes the same endpoint agent session/workspace instead of creating a new session; a new endpoint lifecycle from re-apply creates the next session and writes `previous_sessions.md` so the agent can use older session evidence read-only.
- [x] Same-host restart and minimum-resource guidance validated in a fresh paid RunPod run: `Qwen/Qwen2-0.5B-Instruct` stayed in the same agent session across a local server restart, did not spawn a duplicate Claude process, deployed `qwen2-05b-restart-1110-1`, verified `/v1/chat/completions`, saved a model-level preset recipe, and stopped cleanly. The final service YAML used `gpu: 16GB..24GB:1`; exact RTX 3090 placement belongs under recipe `validations`.
- [x] Endpoint agent stdout is no longer copied to endpoint logs. Endpoint logs are populated from `progress.jsonl` and explicit server lifecycle messages; Claude assistant chatter and final markdown summaries remain in trace/artifacts.
- [x] Endpoint agent logs now start promptly: the server writes an immediate progress line when a detached Claude session starts, stores it in `progress.jsonl`, advances the progress offset to avoid replay, and the prompt requires Claude's first workspace action to be a short progress message before inspecting state/offers/docs. Live smoke `qwen25-log-start-smoke` showed the startup line and Claude's first progress line, then was stopped before any service submission.
- [x] Follow-up paid Qwen2.5 preset-reuse deployment validated the no-Claude path after the model-level recipe format: `Qwen/Qwen2.5-0.5B-Instruct` with `preset_policy: reuse` selected recipe `4a73893b`, deployed on RunPod A5000, reached `running`, answered `/v1/chat/completions`, and stopped cleanly.
- [x] Local duplicate preset files are no longer a planning/list/get inconsistency: the local service merges files by model in memory, `get --json` returns all recipes for the model, `save` collapses duplicates into one canonical file, and `delete` removes all files for that model.
- [x] Broad-fleet vendor-aware harness check: endpoint config used neutral fleet `endpoint-e2e-gpu` with Lambda/Verda/JarvisLabs/RunPod and no endpoint `backends`; current matching offers under `$0.5/hr` were still all RunPod, Claude selected RunPod based on offers, wrote final service resources as `gpu: nvidia:16GB..24GB:1`, verified `/v1/chat/completions`, saved a vendor-aware recipe, and stopped cleanly. Reuse preview after freeing the `nodes: 0..1` fleet slot showed offers without invoking Claude.
- [x] Prompt/guard hardening after repeated YAML mistakes: endpoint prompt and `dstack-prototyping` now distinguish plural service YAML fields (`fleets`, `backends`, `regions`, `instance_types`) from singular CLI flags (`--fleet`, `--backend`, `--region`, `--instance-type`), and the workspace CLI guard returns actionable errors for singular run-config keys before a paid preview/apply can proceed.
- [x] Existing no-spend endpoint functionality e2e: endpoint list/get/logs/stop, endpoint-vs-run command separation, preset list/get, reuse/create/no-fleet apply previews, and preset verbose output. Fixed `dstack endpoint preset -v list` so parent `-v` is not overwritten by the child parser.
- [x] Main learning-loop validation after prompt/guard fixes: `Qwen/Qwen2.5-0.5B-Instruct` with `preset_policy: create` recovered from a real RunPod CUDA driver mismatch, submitted a pinned CUDA-12 vLLM image, verified `/v1/chat/completions`, linked the endpoint to the final run, saved a preset, stopped cleanly, and a subsequent `preset_policy: reuse` endpoint selected the freshly verified recipe, reached `running` without Claude, then stopped cleanly.
- [x] Learned recipe priority fixed: `save_preset` now writes incoming learned recipes before older recipes for the same model, preserving the simple "first recipe with offers wins" planner while ensuring the recipe just proven by the agent is what immediate reuse sees.
- [x] Harder 7B learning-loop validation: `Qwen/Qwen2.5-7B-Instruct` with `preset_policy: create` selected a NVIDIA 24GB..48GB envelope, recovered from no-capacity and a FlashInfer/nvcc runtime failure, deployed `vllm/vllm-openai:v0.24.0` on RunPod RTX A5000, verified `/v1/models` and `/v1/chat/completions`, saved a project-scoped recipe with exact A5000 validation evidence, stopped cleanly, and a no-spend `preset_policy: reuse` preview selected the learned recipe with matching offers without invoking Claude.
- [x] Larger-model learning-loop validation: `Qwen/Qwen3.6-27B` with `preset_policy: create` used current HF/vLLM recipe evidence, chose BF16 TP1 on `gpu: nvidia:80GB:1`, deployed `vllm/vllm-openai:v0.24.0` on RunPod A100 80GB at `$1.39/hr`, waited through 51.1 GiB model loading and CUDA graph capture, verified `/v1/chat/completions`, linked `qwen36-27b-mainloop-1`, and saved a project-scoped preset. The endpoint was stopped cleanly after verification, and a no-spend `preset_policy: reuse` preview selected the saved recipe with 14 matching offers without invoking Claude. This proved the real agent loop can handle a non-trivial current model, not just small smoke models.
- [x] Qwen3.6-27B trace hardened artifact-writing guidance: the agent verified the service correctly, but one final-report string was corrupted from `$1.39/hr` to `.39/hr` by an unquoted shell heredoc. The endpoint system prompt and `dstack-prototyping` skill now require Python serializers or quoted heredocs such as `<<'EOF'` for JSON/Markdown/YAML artifacts.
- [x] Backend-placement/task-first validation: `Qwen/Qwen2.5-7B-Instruct` on fleet `reusable-vs-container` had cheaper RunPod container offers and a JarvisLabs L4 reusable/inspectable offer. Claude chose JarvisLabs despite the slightly higher hourly price, submitted a task first, then promoted a final service that reused the warm L4 instance and verified `/v1/models` plus `/v1/chat/completions`. The endpoint was stopped and the temporary fleet deleted. This proves task-first on a reusable backend, but not the interactive SSH/dev-environment loop.
- [x] Probe-quality correction from the same validation: the task probe observed `nvidia-smi` and host driver evidence but failed on `python` missing before proving framework/runtime/server behavior. The final service still proved the endpoint, but the prompt and `dstack-prototyping` now state that host sanity checks are not recipe proof; a probe must exercise the intended serving stack before service promotion.
- [x] Probe-quality rerun exposed an earlier decision failure before it could test the probe fix: Claude saw RunPod and JarvisLabs offers but inferred "both backends are container-only (no reusable VM/SSH state)", skipped the task/dev probe, and submitted a direct RunPod service. We stopped the endpoint, terminated the service, and deleted the temporary fleet. Prompt/skill now forbid inferring "container-only" or "no reusable state" from offers alone and require uncertainty to be resolved, not treated as proof that a probe cannot help.
- [x] Second probe-quality rerun improved placement and run type but exposed a sharper harness miss: Claude chose JarvisLabs L4 and submitted a task first, but encoded the full investigation as one batch command chain and omitted all optional instance cache mounts (`configuration.volumes=[]`, `runtime.volume_names=[]`). We stopped the endpoint, terminated the task, deleted the fleet, and tightened prompt/skill so attach/SSH-capable probes should be long-lived interactive tasks/dev environments (`sleep infinity` or equivalent) and Hugging Face-style model-serving probes/services should use optional cache mounts or record why they were omitted.
- [x] Third probe-quality rerun showed the limit of prompt-only enforcement: Claude added the optional Hugging Face cache mount, but still generated a batch task instead of a long-lived attach/SSH probe, again wrote `jarvislabs+runpod (container-style)`, and submitted RunPod L4. We stopped the endpoint/run immediately and deleted the fleet. Next fix should be structural: server-generated backend/fleet capability context and possibly a pre-submit guard/required artifact for interactive-probe decisions, not more prose.
- [x] Backend docs-gated rerun validated the intended placement/prototyping path: `Qwen/Qwen2.5-0.5B-Instruct` on fleet `probe-quality-guard` classified JarvisLabs as VM-based from backend docs, rejected RunPod as container-based/no instance volumes, submitted a long-lived task with `sleep infinity`, attached/SSHed into it, verified vLLM locally, stopped the task, reused the idle JarvisLabs L4 for the service, verified `/v1/chat/completions` through the dstack service URL, reached `running`, and stopped cleanly. CLI UX now supports `dstack endpoint logs -w`, and foreground endpoint apply streams the endpoint progress log stream while polling status without `attach`.
- [x] Focused endpoint tests and static checks currently pass (`pytest` endpoint suites, `ruff`, `pyright`).

### Still open for v1

- [ ] Harden the real Claude Code subprocess runtime based on live failures: multi-host restart behavior, duplicate-process prevention across server instances, packaging, and live-run efficiency.
- [ ] Finish runtime durability: final-report handoff after process/server crashes, multi-host reconciliation, and cleanup of non-final submitted runs after restart.
- [ ] Guard learned-preset quality: recipe service `resources` must stay broad enough for reuse but not too loose for correctness, exact hardware must remain in `validations`, and saved presets must be usable without the agent.
- [ ] Add server-generated backend/fleet capability context for the agent workspace: allowed fleets, current nodes/idle instances, backend capability facts known to dstack, whether attach/SSH/dev environments are expected to work, and whether instance cache/volumes are plausible. The last probe-quality run showed that asking the agent to infer this from docs/offers is unreliable.
- [ ] Add a lightweight pre-submit guard or required pre-submit artifact for create-recipe probes: when the chosen experiment is a task/dev probe and attach/SSH is available, the artifact must state whether it will be long-lived/interactive, whether cache mounts are included, and why batch commands are acceptable if used.
- [ ] Run a true interactive SSH/dev-environment scenario on reusable capacity. The JarvisLabs validations proved task-first and better placement, but not the intended long-lived attach/SSH loop, interactive command tuning, optional instance cache mounts, or stronger local server probing before promotion.
- [ ] Decide whether any lightweight preset metadata is worth adding later. Do not add final run ids, recipe sources, or verification summaries to the YAML until a concrete reader uses them.
- [ ] Runtime recipe grounding against vLLM recipes / SGLang docs / HF model cards, with mocked zero-network tests.
- [ ] Endpoint preset inspect polish: keep `dstack endpoint preset get --json` useful enough for exact `validations` and service recipe review without cluttering the compact list output.
- [ ] Real agent runtime dependencies installed automatically by normal server install/deploy paths: local `uv` server installs and server Docker images must include the runtime; no manual post-install dependency step.
- [ ] Endpoint update/version design before in-place updates: a `configuration_version`/deployment guard so stale background workers in multi-server Postgres setups cannot mark a newer endpoint config running.
- [ ] Documentation: endpoint reference schema page, env vars, concepts page, manual e2e runbook, example presets.

### Critical assessment

The endpoint storage/status/preset/run-link side is becoming reasonable. The feature is still not trustworthy because the agent loop and learned-preset quality are not yet proven across repeated real deployments.

Highest current risks:

- Agent works once but saves a preset recipe that is too exact, stale, missing validation evidence, or not reusable.
- Agent wastes budget because hardware selection, offer inspection, experiment choice, or failure recovery is weak.
- Agent logs/traces are either too noisy for users or too thin for debugging.
- Multi-host server restart during `prototyping` can leave ambiguous state or orphan submitted runs if the new server cannot observe the old host's Claude process/workspace.
- Multiple learned recipes for the same model accumulate without an explicit update policy.
- We overfit code around the first Qwen smoke runs before testing enough real model/backends/failure modes.
- One fresh Claude run used macOS-specific `sed -i` and read `~/.dstack/config.yml` to find URL/token for verification; both were prompt/context defects tightened afterward.
- A later fresh Claude rerun fixed those mechanics but failed the higher-level harness test: after service failures caused by FlashInfer runtime JIT, a RunPod provisioning stall, and CUDA 13 package/driver mismatch, the agent kept submitting services instead of switching to a better prototyping path when possible. It also exposed a stop bug: the endpoint became `stopped` while the Claude process continued and submitted another paid run. Process-group abort is now implemented and live-validated; the validation also fixed a zombie-only process-group edge case.
- The latest isolated no-fleet run passed mechanically and showed useful backend/fleet choice, but endpoint logs are still too sparse for watching a real investigation. The next improvement should make the agent write more natural-language decision updates without reintroducing hardcoded labels or templates.
- The latest isolated run also showed that fleet choice needs explicit evidence. `gpu:16GB:1`, `nodes: 0..1`, max price, and idle duration were plausible for a tiny Qwen model, but the harness must make the agent justify which existing fleet/resource envelope it uses without editing fleet configuration.
- Prompt instructions alone are not enough for the fleet/profile contract. The workspace-local CLI guard now enforces allowed fleets and common accepted profile constraints, but this must stay tied to real traces; if we accept more endpoint fields, they must either be enforced by the guard/submitted YAML or explicitly rejected/deferred.
- The 7B existing-fleet run succeeded, but also exposed real harness inefficiency: Claude spawned several concurrent shell polling loops instead of one bounded status loop. This is not just cosmetic; on long deployments it can waste process slots, tokens, and make command traces hard to read.
- Claude's first model API probe used a 420s internal deadline but was killed by Claude Code's 2-minute Bash tool timeout. The agent recovered by checking logs and retrying, but the harness should teach short timed probes and background polling explicitly instead of relying on recovery.
- The service proxy briefly returned `404 Service not found` immediately after service readiness. Claude retried and succeeded, so this is likely a proxy/registration timing edge, but the prompt/runbook should treat early 404s as retryable only after run JSON and service probes indicate the service is registered.
- The fresh Qwen2.5-1.5B RunPod run succeeded mechanically, but still showed prompt/harness gaps: Claude initially omitted the required `fleets` field and depended on the guard to catch it; it used a long polling command that hit the Claude Code Bash timeout; endpoint progress did not include the final "service running" and "model verified" milestones; and the handwritten `final_report.json` contained extra fields with malformed strings. The server ignored the extra fields and used the required schema fields, but future traces should be cleaner.
- The fresh RunPod run did not capture a direct `nvidia-smi` driver string. The service logs proved the cu129 vLLM image ran successfully with CUDA/FLASH_ATTN, which is useful evidence, but validation artifacts should distinguish "runtime worked" from "host driver version recorded."
- The fresh Qwen2-0.5B validation run showed that the latest prompt tightening helped materially, but it also exposed the opposite preset-resource risk. The saved preset is reusable, but because the final service YAML used `gpu: 1`, the recipe service resources had no GPU-memory floor even though validations prove RTX 2000 Ada 16GB. This is not necessarily wrong for a 0.5B model, but the harness needs a sharper rule for when count-only GPU constraints are acceptable versus when a memory envelope is required.
- The fresh Qwen2-0.5B validation run still used logs as part of readiness after an early proxy miss ("wait for Uvicorn running"). That was not fatal because the agent had already checked run JSON and later sent a real model request, but the intended loop is still: run JSON for lifecycle, model API probe for proof, logs for diagnosis/explanation.
- The next fresh Qwen2-0.5B run fixed the resource-envelope issue: the final service YAML used `gpu: 16GB..24GB:1` and the learned recipe kept exact RTX 3090 placement under `validations`. This is a good sign, but not enough to generalize to larger models or multi-replica deployments.
- The same run validated same-host server restart while Claude was running: the server restarted, reused the same agent session/workspace, and did not start a duplicate Claude process. Multi-host restart and Postgres multi-server coordination remain unproven.
- The same run also showed that the workspace CLI guard is necessary: Claude first used `backend` instead of `backends` and omitted `fleets`; the guard blocked preview before spend and Claude corrected the YAML. Treat guard catches as useful safety, but still reduce repeated prompt-level mistakes.
- Endpoint logs leaked Claude assistant stdout even though `progress.jsonl` was clean. The runtime now stops copying assistant stream text to endpoint logs; only progress messages and explicit server lifecycle messages belong there.
- A no-cost reuse preview after the same run selected an older Qwen2 recipe rather than the new resource-envelope recipe. The local store now merges duplicate files into one model-level preset. V1 keeps selection deterministic: try stored recipes in order and use the first one with available offers under the endpoint's effective fleets/profile constraints. Explicit user recipe selection stays Later.
- The 7B main-loop run is a better signal than the tiny Qwen runs: Claude chose a reasonable NVIDIA 24GB..48GB envelope, recovered from no-capacity, diagnosed a FlashInfer/nvcc failure, and produced a reusable recipe. It still showed that the harness should prefer pinned official vLLM serving images for final vLLM OpenAI services unless runtime package installation is itself the experiment.
- The probe-quality rerun showed that prompt-only backend capability reasoning is still fragile. The agent can overrule the intended reusable/inspectable placement route by inventing a backend-capability conclusion from an offer table. We either need stronger prompt/skill constraints or explicit backend/fleet capability context from the server before the agent decides task/dev vs service-first.

### Immediate next steps: repeat the loop, then harden

Do these in order. Do not add more harness surface area until the previous step has produced evidence.

1. **Keep v1 recipe selection simple and deterministic.** Repeated agent tests now leave multiple provisionable recipes for the same model. Local duplicate files are merged. V1 should try recipes in stored order and use the first recipe whose normal run plan has available offers under the endpoint's effective fleets/profile constraints. Do not add quality ranking yet.
2. **Reduce harness waste exposed by guard catches.** The guard must stay, but the agent should not repeatedly write `backend` instead of `backends` or omit required `fleets` from final service YAML.
3. **Harden final-report handoff and submitted-run reconciliation.** Same-host restart while Claude is live now works, but the endpoint worker still needs stronger tests around final report written before link, process/server crash timing, and cleanup of non-final submitted runs.
4. **Deepen the reusable-capacity route.** The JarvisLabs run proved that the agent can prefer a reusable/inspectable backend over cheaper container offers and start with a task. Next, prove the stronger path: when attach/SSH/dev-environment is useful, the agent keeps an interactive probe alive, checks the intended image/runtime/command, and promotes only after the serving stack is actually exercised. Confirm hardware and expected GPU spend before each paid run.
5. **Keep agent budget/cost governance out of v1.** Add it later only with durable per-session accounting and an actually enforced runtime contract; do not expose a config field or env var before that exists.

### How to overcome the current risks

Treat this as a working hypothesis, not a fixed design. After each real endpoint run, update the plan with what actually happened and remove or change tactics that did not help.

| issue | realistic mitigation | evidence to collect | reconsider if |
|---|---|---|---|
| Learned preset works once but is not reusable | Run an immediate preset-reuse test after every successful agent deployment. Validate that the saved recipe `service` can be planned/submitted without the agent and that `validations` are only evidence. | apply plan path selected, offers shown, final service run, endpoint status, model request result, saved preset YAML before/after | the preset path fails for reasons unrelated to transient capacity; then fix preset contract/builder before prompt changes |
| Recipe resources are too exact or too loose | Keep resources sourced from the final service config, but add validation/reporting that flags exact GPU names or full exact CPU/memory/disk constraints in learned recipes unless explicitly justified by the service shape. Do not auto-generalize blindly; first inspect the agent's service YAML and the run plan. | final service YAML, saved service resources, saved validations, offer count before/after, reason for any exact GPU/model constraint | exact constraints repeatedly block reuse, or broad constraints repeatedly schedule hardware that cannot serve the model |
| Agent chooses poor hardware/backend or wastes submissions | Give the agent a required decision trace: model sizing evidence, hardware envelope, current fleet-filtered dstack offers, backend/runtime characteristics inside allowed fleets, planned run resources, and why it is submitting now. Hourly price is a constraint, not the objective: cheaper container placement should not beat a slightly more expensive reusable placement if the reusable path reduces total iteration time, repeated downloads, image churn, or debugging risk. Start with prompt/context; only add server-side enforcement after observed bad behavior is clear. | recipe/model sources, offer table excerpt, chosen resources, rejected alternatives, selected backend placement, selected fleet, command count, elapsed time, GPU spend | the trace is absent or useless in two real runs, or the agent picks a container placement while a viable reusable placement existed without a good reason; then enforce a structured pre-submit decision artifact before paid `dstack apply` |
| Agent uses service submissions as every experiment | Make the prompt/skill require an explicit experiment-type choice. If the uncertainty is package/runtime, launch flags, model load, driver/CUDA compatibility, or backend provisioning and a viable VM/SSH/Kubernetes placement exists inside the allowed fleets, the agent should normally start with a task or interactive experiment before the final service. The agent still makes the final call; this is not a hardcoded rule. | run type per submitted run, why that type was chosen, elapsed provisioning time, whether reusable/inspectable placement was available, service vs task/dev command count, final proof | the agent keeps submitting services for non-URL-wiring uncertainty, or skips a useful task probe without a concrete reason; then add a structured pre-submit artifact that must justify service vs task/dev |
| Agent invents backend capability | Do not let the agent infer "container-only", "no reusable state", or "no SSH/dev value" from an offer table alone. It must use fleet state, backend/fleet behavior evidence, or mark capability as unknown and pick an experiment that resolves the unknown. If this repeats, pass explicit backend/fleet capability context from the server into the agent prompt. | fleet `nodes`/`idle_duration`, current idle/running instances, backend type evidence, agent reasoning line, chosen run type, whether task/dev was skipped | the next live run still misclassifies JarvisLabs/Lambda/Verda/Nebius/SSH/Kubernetes capacity; then make backend capability context server-generated instead of prompt-inferred |
| Task/dev probe is too shallow | Treat `nvidia-smi` and driver strings as host evidence only. A useful probe for service promotion should exercise the selected image or install path, Python/framework runtime, model/auth/cache access when feasible, server start on the intended port, and a local health or model API request if possible. If the probe exits before those checks, classify it as failed/inconclusive and either fix the probe or continue experimenting before promotion. | task/dev config, logs, driver evidence, framework import/version, model download result, local server/probe result, final service verification | two runs over-interpret partial probes; then require a structured pre-promotion artifact before the agent may submit the final service |
| Agent assumes global offers are usable | Enforce at the CLI boundary, not only in prompt text. The workspace-local `dstack` shim blocks fleet applies and blocks `dstack offer` / run applies that omit allowed fleets or violate accepted endpoint profile constraints. | fleet list/get output, fleet-filtered offers, backend/hardware reasoning, whether submitted configs carry the allowed fleet/profile constraints, cleanup, CLI guard block output | agent still finds a path around the guard, creates/edits a fleet, or submits a run outside allowed constraints |
| Host driver/CUDA compatibility is invisible in offers | Treat driver/runtime compatibility as uncertainty. Some backends vary host drivers by provider, GPU pool, region, or node, and dstack fleets/offers may not expose it. The agent should infer risk from provider/GPU/region evidence when possible and verify with `nvidia-smi`, run JSON/logs, dev environments, or one-shot tasks before trusting unpinned package installs. | `nvidia-smi`/driver evidence, package/image CUDA requirements, provider/GPU/region evidence, failed log root cause | driver mismatch recurs on the same provider; then bias recipes toward known-compatible images/package pins or avoid that offer class |
| Agent logs are noisy or unhelpful | Split logs into two layers: endpoint log gets natural-language decision updates authored by the agent; workspace trace stores command output, YAML, raw logs, and final report. Do not impose labels/categories/templates, and do not put full CLI output or service logs in endpoint logs. | `dstack endpoint logs <endpoint>` readability, workspace artifacts, ability to diagnose failure without server stdout | endpoint logs still duplicate/replay, hide important state, force reading server logs for normal debugging, or stay too sparse to follow the investigation |
| Restart during `prototyping` duplicates work or loses the final run | Same endpoint configuration lifecycle reuses the same agent session/workspace; dead same-host Claude processes are relaunched in that workspace; new endpoint lifecycle creates the next session and passes older session summaries as read-only context. Still reconcile before launch: process metadata, final report, endpoint submission rows, linked `service_run_id`, and live submitted runs. | restart test with a live process, restart test after final report before link, endpoint submissions, linked run, no duplicate paid process | reconciliation logic becomes fragile, or multi-host restarts cannot observe enough process/workspace state; then consider moving agent execution to a separately tracked durable task model |
| Stop during `prototyping` leaks resources | Add process cancellation and submitted-run cleanup using `EndpointRunSubmissionModel`, not name heuristics. Endpoint stop should request abort, stop linked/submitted non-terminal runs, then finish through the normal run lifecycle. | stop during Claude process, stop after a submitted run appears, final run statuses, endpoint stopped, no running GPU run | cancellation depends on runtime behavior we cannot rely on; then isolate agent execution in a managed process/task with explicit supervisor state |
| Agent cost governance is not durable yet | Keep budget/cost accounting out of the v1 public endpoint schema. Add it later only when the runtime exposes reliable usage and dstack persists spend per endpoint agent session before any resume/retry starts another process. | Claude reported usage/cost, persisted session spend, refusal path when exhausted | Claude Code cannot expose reliable usage data; then use a stricter wall-clock/process cap plus operator-visible warning until runtime changes |
| Multiple learned recipes accumulate | Keep recipe selection simple: use the first stored recipe that has available offers under the endpoint's effective fleets/profile constraints. When the agent saves a newly verified recipe, store it before older recipes so immediate reuse sees the latest proof. Do not delete or rewrite older recipes until the harness can prove they are not reproducible under their claimed conditions. | recipe list by model, service resources, validation evidence, reuse success/failure per recipe, whether the freshly saved recipe is selected by a no-spend preview | users need control over a specific recipe; then add an explicit later `recipe: <num>` endpoint option before adding automatic ranking or update policy |
| Agent harness design overfits early Qwen runs | Maintain a scenario ladder: one tiny public model, one slightly larger common model, one gated/HF-token model, one no-offers/constraint case, one failure-cleanup case. Change harness only after comparing patterns across at least two scenarios unless the bug is clearly blocking. | per-scenario run notes, failure categories, command counts, spend, preset reuse result | the first two scenarios expose contradictory needs; then pause and rework the harness contract rather than patching locally |

Near-term implementation strategy:

1. Prefer prompt/context and artifact requirements for the first two real runs. They are cheaper to change and reveal what the agent naturally does.
2. Add server-side validation only where the failure would be expensive or dangerous: wrong project/user run, missing service `model`, missing final verification, leaked non-terminal runs, invalid preset shape.
3. Keep every hardening change tied to a reproducible trace: command transcript, endpoint log, final report, saved preset, and dstack run state.
4. After each real run, classify the issue as one of: dstack/backend provisioning bug, agent decision bug, prompt/context gap, preset contract bug, lifecycle/recovery bug, or UX/logging bug. Fix the right layer; do not let agent failures hide dstack/backend failures.
5. Be willing to change runtime approach if Claude Code cannot reliably run non-interactively, expose usage, cancel, preserve artifacts, or package cleanly in server installs/Docker.

### Adjusted from the original plan

- Preset service responsibility was narrowed to **storage only**. Matching, planning, and service apply live outside `EndpointPresetService`.
- Presets are now model-level files with one or more `recipes`. The recipe `service` is the scheduling source of truth; `validations` store exact running replica resources in service replica-group order.
- New learned GPU recipes should be vendor-aware because serving recipes are not portable across accelerator vendors. Existing vendorless local recipes are preserved on read; the agent harness is responsible for authoring vendor-aware final service YAML, and the learned-preset builder may fill the vendor from exact validation hardware before saving.
- Presets do **not** store backend, region, or instance type in v1. They store service resource requirements plus exact validation evidence that can be replanned against current fleets.
- A learned recipe records how many registered running replicas existed per replica group at save time through `validations[*].replicas[*].resources`. Autoscaling metrics, scaling validation, and benchmark metadata are Later.
- Preset matching does **not** force `creation_policy: reuse`; default `reuse-or-create` may use elastic fleets that can provision new instances.
- Endpoint plan `preset_policy` remains the configured/default policy; the selected path (`preset`, `agent`, or `none`) is represented only by `provisioning_plan`.
- Endpoint config changes are handled like current run UX: prompt to stop/override, with the backing service cleanup performed server-side. In-place update/rolling redeploy is Later.
- Later endpoint config updates must reuse the existing service-run `get_plan`/`apply_plan`/rolling deployment machinery, and endpoint DB updates must be guarded by a configuration/deployment version for multi-server safety.
- Endpoint-level `resources` are not part of v1. V1 placement constraints are the accepted `ProfileParams` plus the preset/service resources. If endpoint `resources` are added later, they must be a hard constraint with clear merge semantics for single-service and replica-group services; they must not be a prompt-only hint.
- Stop/override applies only to non-terminal existing endpoints. Terminal endpoints are replaceable like finished runs.
- Serving-run-name lookup is a conflict check for non-terminal runs only. Terminal conflicting runs follow normal run submission semantics: the run apply path can delete/recreate them, while endpoint code must not adopt/delete unrelated runs by name.
- No generic server-side endpoint health probe in v1. Existing service probes/registration are the server readiness source. In the agent path, the agent itself must perform final functional verification before reporting a final service.
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
     └─ endpoint: PROTOTYPING (agent investigates/deploys, for the create-recipe path)
     └─ endpoint: PROVISIONING (service run starting, model pulling, service probes passing)
     └─ endpoint: RUNNING (service has a registered running job and model URL)
```

The endpoint's deliverable is an OpenAI-compatible base URL (from the backing service's `ServiceSpec.model.base_url`).

### v1 scope (this plan)

- New configuration type + DB model + REST API + CLI (`dstack apply`, `dstack endpoint list|get|logs|stop|preset`).
- `EndpointPipeline` background processing: SUBMITTED → PROTOTYPING/PROVISIONING → RUNNING/FAILED, STOPPING → STOPPED, crash recovery, and ownership-safe reconciliation.
- Preset subsystem: `EndpointPresetService` interface + local-directory implementation for storing/loading presets; endpoint planning code separately matches loaded presets against existing fleets, including elastic fleets that can provision new instances, via the run planner; successful agent deployments are saved back as sanitized local presets.
- Agent subsystem: `AgentService` interface + real Claude agent runtime implementation, a CLI-first execution workspace that lets the agent use the real `dstack` binary, vendored prompt/context, recipe/hardware grounding, and a minimal structured handoff for the final service. Raw LLM API loops are not accepted for v1.
- Endpoint readiness follows the backing dstack service lifecycle on the server side: a service run is usable once it is RUNNING, has a registered running job, and exposes a model URL. The agent path additionally requires the agent to verify the final service with a model request before reporting success; the server does not add a generic duplicate endpoint probe in v1.
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
    PROTOTYPING = "prototyping"      # server agent is investigating/deploying
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
  - `type="preset"`: a **provisionable preset recipe** was selected. This includes `preset_model`, `recipe_id`, `service_name`, and `job_offers: list[EndpointPlanJobOffers]` derived from `runs.get_plan` (enough for the CLI to print the selected preset/recipe, stable run-like scheduling properties, and first matching offers, without dumping the full run plan).
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
  - Plan output: keep it close to run apply. Print one stable properties table: project, user, configuration path, type, spot policy, max price, preset policy, and preset model/recipe only when a provisionable recipe was selected. Do not show model, action, endpoint name as a separate row, resources as a separate property, backing service name, agent internals, or a separate "Provisioning" section. If a provisionable recipe matched, print offers underneath using the run-style offers table; that offers table is where the concrete resource information belongs. If only no-offer recipes matched, print one short message below the table; with `reuse-or-create` and an available agent, continue to the agent path.
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
  - `WHERE status IN (SUBMITTED, PROTOTYPING, PROVISIONING, STOPPING) OR (status == RUNNING AND last_processed_at <= now - ENDPOINT_RUNNING_CHECK_INTERVAL)`
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
SUBMITTED ──(no preset, agent on)─────────────────► PROTOTYPING (method=agent)
SUBMITTED ──(preset_policy=reuse; no preset)──────► FAILED "No matching endpoint presets found."
SUBMITTED ──(effective policy=create; agent off)──► FAILED "No matching endpoint presets found. Preset
                                                            policy create requires the server agent,
                                                            but DSTACK_AGENT_ANTHROPIC_API_KEY is not set."
PROTOTYPING ─(agent reports verified service run; run not ready yet)──► PROTOTYPING (service_run_id linked)
PROTOTYPING ─(linked run RUNNING + replica registered + model URL)────► RUNNING
PROVISIONING ─(preset run RUNNING + replica registered + model URL)► RUNNING
PROVISIONING ─(run finished/soft-deleted)──────────────────────────► FAILED
RUNNING ─(run gone/failed/deleted)─────────────────────────────────► FAILED (stop backing run)   # later: agent retry policy
any ─(stop requested)──────────────────────────────────────────────► STOPPING → stop linked backing run → STOPPED
```

V1 does **not** automatically retry failed provisioning attempts. A backing run that finishes or fails before readiness makes the endpoint FAILED.

#### `_process_submitted_endpoint`
1. Parse `EndpointConfiguration`; ask endpoint planning code (`planning.py::find_matching_preset_plan(...)`) to list presets through `EndpointPresetService`, build candidate run specs, and call the run planner (§7).
2. If a provisionable preset recipe matches: check the run name in that selected plan. A non-terminal run conflict that is not the linked `service_run_id` fails with a clear message; terminal conflicts are left to normal run submission, which can recycle them like service apply. Then submit the matching plan in a fresh session as the endpoint's creator user through a small internal helper that mirrors the run router (`refresh_ssh_key` if needed, `get_plan`, then `apply_plan`/`submit_run` with the same policy-applied spec), and return `{status: PROVISIONING, provisioning_method: f"preset:{preset.model}#{recipe.id}", service_run_id: run.id}`. `register_service` runs synchronously during submission and can raise (`FORBID_SERVICES_WITHOUT_GATEWAY`, referenced gateway missing) — catch `ServerClientError` ⇒ FAILED with the message.
3. Else if agent enabled (`settings.AGENT_ANTHROPIC_API_KEY` set and the real agent runtime is available): return `{status: PROTOTYPING, provisioning_method: "agent"}` — the agent runs in the PROTOTYPING handler (keeps SUBMITTED processing fast and makes long agent work visible in CLI/API). Do not block this path on the preset path's deterministic service-run-name convention; the agent uses strict numbered submission names, and the server links the final run by ID after validating project/user/config.
4. Else FAILED (message above; if the key is set but the runtime is unavailable, say the server agent implementation/runtime is unavailable; normal server installs and Docker images must include runtime dependencies once the implementation lands).

#### `_process_provisioning_endpoint` — reconcile-first
1. **If `service_run_id` set**, load the run (treating `run.deleted == True` as "run gone"):
   - run `RUNNING`, ≥1 replica job with `registered == True`, and `ServiceSpec.model.base_url` exists → if `provisioning_method == "agent"`, save a sanitized preset from the backing run (§7.4), then `RUNNING`. This deliberately relies on the existing service probe/registration path rather than adding a second endpoint probe.
   - run in `finished_statuses()` or soft-deleted → FAILED with the run error/status. Automatic retry is Later.
   - run `TERMINATING` → no-op (wait).
   - run still starting (SUBMITTED/PROVISIONING/PULLING) → no-op; stay PROVISIONING.
3. **PROTOTYPING / no run yet + method=agent** — the long step:
   a. Before launching or relaunching the agent, reconcile the endpoint workspace, existing final-report artifacts, endpoint submission rows, and live submitted/final runs. Same endpoint configuration lifecycle reuses the same agent session/workspace; if the same-host Claude process is gone without a terminal report, the server relaunches Claude in that workspace so it can resume from artifacts and submitted-run evidence. A new endpoint lifecycle starts the next session and gives the agent `previous_sessions.md` as read-only context. Cleanup of endpoint-submitted runs must use explicit `EndpointRunSubmissionModel` rows, never name matching.
   b. Run `AgentService.provision_endpoint(...)` (§8) inside the worker — heartbeater keeps the lease alive while the agent subprocess runs. Stop-time cancellation exists for same-host Claude processes; multi-host restart/supervision remains a hardening item. Do not add a generic endpoint provisioning timeout here; real agent-session budgets belong inside the harness once token/cost/spend semantics are defined.
   c. On structured success `{run_id}`/linked service run → set `service_run_id` and keep status `PROTOTYPING` until the linked service run also satisfies normal dstack service readiness. Once ready, save the learned preset and mark the endpoint `RUNNING`. On failure/abort → FAILED with the agent's summary in `status_message` + stop only the linked service run; cleanup of non-final submitted runs must use explicit endpoint submission records, not name matching.
4. **No run yet + method=preset**: reachable only if the preset run vanished before the endpoint recorded its linked service run — FAILED. Automatic retry is Later.

#### `_process_running_endpoint`
Runs at the slower RUNNING cadence (`ENDPOINT_RUNNING_CHECK_INTERVAL`, default 60s):
1. Run liveness: backing run missing/soft-deleted/`finished_statuses()`/`TERMINATING` ⇒ FAILED "Backing service run <name> is <status>" (v1; re-provisioning is a Later "agent retry policy" item). This also catches out-of-band `dstack stop`/`delete` of the run by users.
2. No generic server-side endpoint model probe in v1. The backing service owns probes and registration for lifecycle readiness. In the agent path, the agent must make a final model request and include the result in its final report before the server links the final service.

**Rule: every transition to FAILED issues a one-shot `stop_runs(abort=False)` for a still non-terminal backing run** (RunPipeline completes the termination asynchronously; no waiting needed since FAILED endpoints aren't re-fetched). Stopping a FAILED endpoint later is a no-op unless a linked run still needs cleanup.

#### `_process_stopping_endpoint`
Two-phase, server-side, and intentionally simple in v1: (1) backing run present and not finished → `stop_runs(abort=False)` once, then no-op wait on subsequent iterations while the normal RunPipeline terminates the run. (2) run finished (or absent/deleted) → write `{status: STOPPED}`, keep the endpoint row visible in history, and emit "Endpoint stopped". Forced abort/escalation for stuck stopping is Later, not required for v1.

### 6.3 Crash recovery summary

Replica dies mid-step ⇒ heartbeats stop ⇒ lease expires (≤ ~30s) ⇒ another replica re-fetches the row. V1 handlers are idempotent around the linked `service_run_id`; preset-run-name conflicts are treated as conflicts, not ownership. `EndpointAgentSessionModel` tracks the current Claude process/workspace for an endpoint configuration lifecycle. `EndpointRunSubmissionModel` preserves dstack runs created by that session so recovery does not rely on fragile name heuristics. Agent session budgeting is Later and should be explicit to the agent harness, not a generic endpoint provisioning timeout. Automatic retry is Later.

### 6.4 Endpoint-level model probes (deferred)

Do **not** add a generic endpoint probe loop in v1. Service configurations already own probes, and `JobModel.registered` is the service readiness signal after those probes pass. Adding a second endpoint probe loop duplicates service behavior, introduces token/base-URL/proxy/network ambiguity, and makes endpoint lifecycle less conventional for dstack.

Later, server-side endpoint retry/hardening may add its own explicit verification before re-saving a learned preset or marking an endpoint running again. If/when that is added, prefer reusing the existing in-process probe machinery (`scheduled_tasks/probes.py::_execute_probe` and `get_service_replica_client`) rather than probing through the public service URL.

### 6.5 Run identity & linkage (decision)

- **Backing service run name**: the preset path uses `get_endpoint_serving_run_name(endpoint.name)` (`<endpoint>-serving` when it fits, otherwise the endpoint name) because the server submits that service itself. The agent path uses numbered endpoint submissions: `<endpoint>-1`, `<endpoint>-2`, and so on. In both paths, `EndpointModel.service_run_id` is the authoritative link for readiness, URL derivation, logs, and v1 cleanup. Name lookup is not an ownership proof and must not be used to adopt or destroy a run.
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
- `EndpointRunSubmissionModel` is endpoint-submitted run history, not the serving-run selector.
- Preset-path run-name lookup remains conflict detection for non-terminal runs only. CLI/user confirmation may stop that conflicting run, but the background worker must not auto-adopt or auto-delete it by name.

Implementation notes:
- `runs.apply_plan()` can commit internally, so preset-path endpoint code records the submission immediately after a run is accepted and before moving on.
- In the agent path, Claude records every submitted dev environment, task, or service in `submissions.jsonl`. The server reconciles strict numbered submitted run names and reported run IDs into `EndpointRunSubmissionModel` rows; non-strict names are ignored for ownership and cleanup.

---

## 7. Preset subsystem

Storage and parsing live in `src/dstack/_internal/server/services/endpoints/presets.py`.
Preset matching and run-plan construction live in `src/dstack/_internal/server/services/endpoints/planning.py`.

### 7.1 What a preset is

A preset is a **model-level set of tested deployment recipes**. It is not a single generated name and it is not only a service YAML. The model is the lookup key; each recipe has an internal `id`.

In v1 the local file is a small wrapper around:
- `model`: the endpoint model this preset satisfies and the matching key;
- `recipes`: one or more tested deployment recipes for the model;
- `recipes[*].service`: the serving recipe, service shape, and scheduling resources used for reuse/offer matching;
- `recipes[*].validations`: exact verified hardware evidence from successful deployments, ordered to match `service.replica_groups`.

The wrapper is deliberate: a recipe is compiled directly into a normal `ServiceConfiguration` before calling the existing run planner. There is no new scheduler path. The service section owns resources because that is already how dstack services describe placement; validations are evidence, not scheduling input.

Homogeneous service example (`qwen3-32b-vllm-h100x4.dstack.yml`): no explicit `service.replicas` list means there is one implicit service replica group. `validations[0].replicas[0].resources` records the exact resources of each running replica observed when the recipe was verified.

```yaml
type: endpoint-preset
model: Qwen/Qwen3-32B
recipes:
  - id: 8f3a12c4
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
      resources:
        shm_size: 16GB
        gpu: nvidia:H100:4
    validations:
      - replicas:
          - resources:
              - cpu: 64
                memory: 512GB
                disk: 200GB
                gpu: nvidia:H100:80GB:4
```

Replica-group example: `validations[*].replicas` is sorted in exactly the same order as `service.replica_groups`. There is no separate group name because service replica-group order is already explicit. This supports existing dstack services with different resource specs per group without making v1 responsible for inventing advanced serving architectures.

```yaml
type: endpoint-preset
model: Qwen/Qwen3-32B
recipes:
  - id: 4c38b901
    service:
      port: 8000
      model: Qwen/Qwen3-32B
      replicas:
        - name: router
          count: 1
          image: ghcr.io/example/router:latest
          commands:
            - python router.py
          resources:
            cpu: 4
        - name: worker
          count: 2
          image: vllm/vllm-openai:latest
          commands:
            - vllm serve Qwen/Qwen3-32B --host 0.0.0.0 --port 8000
          resources:
            shm_size: 16GB
            gpu: nvidia:H100:4
    validations:
      - replicas:
          - resources:
              - cpu: 8
                memory: 16GB
                disk: 100GB
                gpu: 0
          - resources:
              - cpu: 64
                memory: 512GB
                disk: 200GB
                gpu: nvidia:H100:80GB:4
              - cpu: 64
                memory: 512GB
                disk: 200GB
                gpu: nvidia:H100:80GB:4
```

V1 constraints:
- `service` must not contain `name` or `ProfileParams`. Endpoint `ProfileParams` constrain placement/fleets/pricing on top of the recipe service.
- `service` must contain resources either at the top level or on every explicit replica group. Those resources are the scheduling contract used by reuse planning.
- New learned GPU service resources should specify a vendor. The agent harness should write a broad vendor-aware requirement such as `gpu: nvidia:16GB..24GB:1` after it chooses or verifies NVIDIA hardware. The loader preserves existing vendorless local recipes, but explicit vendor conflicts with validation evidence are invalid.
- `validations[*].replicas` order is part of the contract. If `service.replicas` is a list, `validations[*].replicas[i]` corresponds to `service.replicas[i]`. If there is no replica-group list, each validation has exactly one implicit replica group.
- Each validation replica group contains `resources: list[ResourcesSpec]`, one exact entry per verified running replica/instance in that group.
- Hardware alternatives, benchmarked variants, automatic recipe updates, and metrics on validations are Later.

### 7.2 Interfaces

```python
class EndpointPreset(CoreModel):
    model: str                             # matching key
    recipes: list[EndpointPresetRecipe]

class EndpointPresetRecipe(CoreModel):
    id: str                                # hash of normalized service recipe in v1
    service: ServiceConfiguration          # compiled service config without name/profile fields
    validations: list[EndpointPresetValidation]

class EndpointPresetValidation(CoreModel):
    replicas: list[EndpointPresetValidationReplica]
    """Ordered to match `ServiceConfiguration.replica_groups`."""

class EndpointPresetValidationReplica(CoreModel):
    resources: list[ResourcesSpec]         # exact resources for running replicas in this group

class EndpointPresetService(ABC):          # storage abstraction only — local dir first, S3/git later
    @abstractmethod
    async def list_presets(self, project_name: str) -> list[EndpointPreset]: ...

    @abstractmethod
    async def get_preset(self, project_name: str, model: str) -> Optional[EndpointPreset]: ...

    @abstractmethod
    async def delete_preset(self, project_name: str, model: str) -> None: ...

    @abstractmethod
    async def save_preset(self, project_name: str, preset: EndpointPreset, comments=None) -> EndpointPreset: ...

class LocalDirEndpointPresetService(EndpointPresetService):
    """Reads *.yml/*.yaml from settings.SERVER_PROJECTS_DIR_PATH / project_name / "presets".
    Re-reads per call; file IO via run_async.
    Invalid files are logged and skipped, never fatal."""

class EndpointPlanJobOffers(CoreModel):
    replica_group: str
    offers: list[InstanceOfferWithAvailability]  # capped by max_offers
    total_offers: int
    max_price: Optional[float]

@dataclass(frozen=True)
class EndpointPresetPlan:                 # planning.py, not presets.py
    preset: EndpointPreset
    recipe: EndpointPresetRecipe
    run_plan: RunPlan
```

Module-level `get_endpoint_preset_service()` returning the configured implementation (test-injectable).

### 7.3 Matching & submission

This is endpoint planning/orchestration logic, not `EndpointPresetService` storage logic.

`planning.py::find_matching_preset_plan(session, project, user, endpoint_name, endpoint_conf, preset_service=None) -> Optional[EndpointPresetPlan]`:
1. Candidates: presets whose top-level `model` equals `endpoint_conf.model` case-insensitively, in sorted file-name order. If there are no candidates, return `None` without refreshing the user's SSH key or calling the run planner.
2. For each candidate recipe, build the merged service config (below), wrap in a `RunSpec` (repo fields `None` → virtual repo; `RunSpec.profile` is Optional), and call `runs.get_plan(session, project, user, run_spec, max_offers=1)`. Use the endpoint's effective `creation_policy`; if omitted, keep the normal run default `reuse-or-create` so elastic fleets may provision new instances. If the user explicitly sets `creation_policy: reuse`, matching becomes existing-instances-only. Match ⇔ every `job_plan` has ≥1 offer with `offer.availability.is_available()`.
   - Before plan/submission, mirror the run router's behavior: if the creator user has no `ssh_public_key`, call `users.refresh_ssh_key(...)` rather than failing the endpoint. This keeps endpoint apply consistent with `dstack apply` for services.
   - **Wrap each candidate in `try/except ServerClientError` → skip**: `get_plan` validates the merged config and can raise for a bad preset; one bad preset must not abort matching.
   - Cost note: the planner enumerates cloud backend offers per candidate cloud fleet (`plan.py::get_job_plans` → `find_optimal_fleet_with_offers`) — each candidate evaluation can take seconds. This is acceptable in `/get_plan` and the pipeline only because matching filters by model before planning and uses `max_offers=1`; keep the local preset set small and do not broaden matching into a registry scan in v1.
   - Known under-check, accepted for v1 (matching is advisory): `runs.get_plan` produces one representative `JobPlan` per replica group (`replica_num=0`), while validations may record multiple exact running replicas per group. V1 verifies each group has at least one available matching offer for the recipe service resources and leaves full cardinality/capacity checks to the run scheduler. Capacity-aware matching over every validation replica is Later.
3. First match wins.

`EndpointPresetPlan` contains the selected `EndpointPreset`, selected `EndpointPresetRecipe`, and the `RunPlan` computed from the merged `RunSpec`. The caller must submit that same plan/spec path rather than rebuilding independently, mirroring the run apply split between `runs.get_plan` and `runs.apply_plan`.

Merged service config (preset → endpoint overrides):
- start from the selected recipe's `ServiceConfiguration`;
- `name = get_endpoint_serving_run_name(endpoint.name)` (the backing service run name);
- merge `endpoint.env` **over** preset env (`Env.update`); endpoint env arrives fully resolved (sentinels rejected at create);
- copy every non-`None` `ProfileParams` field from `EndpointConfiguration` onto the service config (both inherit `ProfileParams`, so this is a field-loop like `RunSpec._merged_profile`, `core/models/runs.py:590-607`);
- do **not** merge or override resources from the endpoint: endpoints do not expose resources in v1, and the recipe service resources are the tested scheduling requirements;
- do not force `creation_policy = reuse`: the normal default `reuse-or-create` is intentional because existing dstack fleets may be elastic and allowed to provision new instances for submitted services/jobs.

How this runs without the agent: the selected recipe service is already a normal `ServiceConfiguration` without a name/profile. The endpoint layer sets the backing service name and endpoint/profile constraints, then normal run planning/submission decides how many replicas to start and where to place them. `validations` record verified running replica counts/resources at save time; they are evidence and future inspect/JSON input, not a replacement for service `replicas`/autoscaling.

Submission: `RunSpec(run_name=get_endpoint_serving_run_name(endpoint.name), configuration=merged, ssh_key_pub=None)` as the creator user, using the same policy/SSH-key behavior as the run router (`refresh_ssh_key` if needed; do not let `get_plan` and the final run submission see different specs). If validation still fails, surface that as endpoint FAILED.

Fleet-drift note: matching is advisory — a fleet can become busy between match and provisioning. No hard endpoint→fleet binding.

### 7.4 Saving agent-proven presets (v1)

When an agent-created backing service becomes `RUNNING` through the normal service readiness path, save a sanitized `endpoint-preset` wrapper back into the endpoint project's local preset directory (`<server dir>/projects/<project name>/presets`). This makes the second endpoint for the same model in the same project take the deterministic preset path instead of paying the agent again.

Implementation details:
- Extend `EndpointPresetService` with project-scoped operations such as `save_preset(project_name, preset, comments) -> EndpointPreset`. The local implementation writes a `type: endpoint-preset` YAML file under `settings.SERVER_PROJECTS_DIR_PATH / project_name / "presets"` using an atomic temp-file rename. File names are derived from the model; lookup and merge are by `model`.
- Source of truth is the backing run's stored `RunSpec.configuration` plus the latest successful job submissions after the service has reached `RUNNING`, not the agent's final text. Sanitize before writing: top-level `model` comes from the verified service model; `recipes[*].service` preserves the serving recipe/shape fields (`image`, `commands`, `port`, `model`, `resources`, `volumes`, `replicas`, probes, scaling) but clears `type`, `name`, and `ProfileParams`; `recipes[*].validations[*].replicas[*].resources` are built from jobs grouped by `JobSpec.replica_group` in `ServiceConfiguration.replica_groups` order, deriving each exact instance `ResourcesSpec` from `JobRuntimeData.offer` when present or the backing `InstanceModel.offer` as fallback. Merge env as names only for endpoint-provided keys and redact secret-looking values (`TOKEN`, `KEY`, `SECRET`, `PASSWORD`) to name-only entries. Never write resolved secret values from `EndpointConfiguration.env` to disk.
- Keep YAML metadata minimal in v1. Comments may note the generating endpoint/run, but there is no structured metadata object until a concrete reader uses it.
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
- *Termination contract*: the agent returns a structured final report with success/failure, final service run name/id, final service YAML/content, recipe sources, and verification summary. The agent is responsible for final functional verification. The server does not trust the report blindly; it validates the claimed run identity and project/user ownership before linking the run, then waits for normal dstack service readiness before activating the endpoint. The readiness gate is bookkeeping, not a server-side claim that the model works.
- *Environment hygiene*: the agent runtime receives only the credentials it needs to authenticate to Claude plus the isolated dstack CLI config for the target project. The command/workspace environment remains scrubbed: do not expose server DB credentials, encryption keys, cloud backend credentials, or unrelated server env vars.
- *Abortability and restart*: endpoint stop aborts same-host Claude process groups and stops linked/submitted runs through endpoint submission rows. Same-host restart/resume reuses the existing agent session/workspace. Multi-host restart/supervision, duplicate-process prevention across server instances, and final handoff edge cases still need hardening before production use.

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
5. choose the experiment type deliberately: dev environment, task, or service;
6. preview with `dstack apply -f <config.yml>` before spending GPU time;
7. submit detached with `dstack apply -f <config.yml> -y -d` only when the plan is acceptable within the endpoint/profile envelope;
8. debug with `dstack ps`, `dstack run get <run> --json`, and `dstack logs`;
9. stop ruled-out submitted runs with `dstack stop <run> -y` and let normal run lifecycle handle termination/deletion;
10. finish only after the final service is RUNNING, has a registered replica, exposes a model URL, and the agent has made a final model request proving the requested model is actually served.

This is intentionally **not** a new server-side mini API for dstack. The harness should provide:
- an endpoint-scoped working directory for service YAMLs, notes, and command transcripts;
- the real `dstack` binary from the running installation;
- a CLI config/context that targets the correct server, project, and endpoint creator user;
- endpoint constraints: model, env names, ProfileParams, preset policy, and allowed fleet/profile envelope;
- recipe grounding guidance and optionally preloaded recipe/context snippets, not a required `find_model_recipes` tool;
- command logging and a `should_abort()` check between command iterations so deletion can interrupt long agent work;
- a structured final-report schema.

The preset path uses a server-owned deterministic run name from `get_endpoint_serving_run_name(endpoint.name)` because the server submits that service itself. The agent path uses a strict submission naming contract for every dstack run Claude creates: `<endpoint-name>-1`, `<endpoint-name>-2`, and so on. Claude still decides what each run is for; framework, hardware, purpose, and role details belong in `submissions.jsonl`, progress messages, `verification.json`, and the final report, not in the run name. The server validates and links the final service by reported run ID, then records it in `EndpointModel.service_run_id` and `EndpointRunSubmissionModel`.

Dev-environment and task prototyping are not a side path; they are part of the intended harness. The agent should submit a service directly only when the recipe/image/command/resources are already known enough that URL wiring and final service behavior are the main remaining question. If failures show package/runtime compatibility, launch flags, model load, driver/CUDA mismatch, or backend provisioning uncertainty, the next experiment should often use a reusable fleet path, dev environment, or small task when that can avoid repeated cold provisioning. Warm idle instances can speed services too, not only dev environments. This remains agent judgment, not a hardcoded retry rule. For container-only backends that cannot reuse instances, the agent may still use tasks/services, but should avoid resubmitting the same service shape just to learn basic runtime facts. A probe only counts if it exercises the intended serving stack deeply enough to justify promotion; a host-only check such as `nvidia-smi` is not enough. The clean service is still the final proof, and failed final service verification must send the agent back into the evidence loop instead of producing success.

Endpoint agents do **not** create fleets. This is a product contract, not just prompt preference: the endpoint apply plan and server create path require at least one active existing fleet usable by the endpoint. By default the agent may consider all existing project/imported fleets; endpoint `fleets` narrows that set. If no active fleet exists, the plan/create path reports "The project has no fleets. Create one before submitting an endpoint." If `fleets` is set but none match, it reports that no fleets match the endpoint configuration.

Within that contract, fleet/backend/hardware choice is still the agent's decision. It should inspect existing fleets, pass applicable `--fleet` filters to `dstack offer`, plan previews, and submitted runs, and choose among the allowed fleets based on the model, endpoint/profile constraints, offer envelope, current fleet state, and experiment. The agent must not create, delete, apply, or edit fleets, including `nodes`, `target`, `idle_duration`, backends, resources, max nodes, or ownership. If the allowed fleets cannot support a useful experiment, it should fail with clear evidence for the user/admin.

Driver/runtime compatibility is a first-class uncertainty. Some backends expose different host NVIDIA driver/CUDA compatibility across provider pools, regions, GPU generations, or individual nodes, and dstack offers/fleets may not expose that version. The agent may estimate likelihood from provider/GPU/region evidence, but when CUDA/runtime compatibility matters it should gather evidence (`nvidia-smi`, run logs, dev environment/task probe, or known-compatible image/package sources) before trusting unpinned framework installs. This evidence belongs in agent artifacts and future validation metadata; it must not become a fake scheduling constraint unless the backend/user constraints can actually enforce it.

For v1, advanced P/D disaggregation, multi-service routers/workers, load benchmarking, and autoscaling tuning are Later unless needed to make the requested model serve at all.

### 8.4 Prompt, recipe grounding & vendored context

Runtime context layout:

- `resources/system_prompt.md` — endpoint-specific mission and protocol only: use the real CLI, load `/dstack` and `/dstack-prototyping`, honor endpoint constraints, emit free-form natural-language progress updates, verify the final model API request, and return the structured final report.
- repo-root `skills/dstack/SKILL.md` — CLI/config source of truth.
- repo-root `skills/dstack-prototyping/SKILL.md` — reusable research-to-working-workload skill: source order, model-serving recipe selection, hardware fit, dev-environment/task/service experiment choice, failure classification, final service cleanup, and model API verification.

`pyproject.toml` force-includes repo-root `skills/**` into wheels/sdists. The workspace setup locates that packaged `skills` directory and copies only `dstack` and `dstack-prototyping` into `.claude/skills` for each endpoint-agent run. The prompt explicitly names `/dstack` and `/dstack-prototyping`; do not rely on an operator's user-level Claude/Codex skills.

`dstack-prototyping` should answer both "how do I experiment on dstack?" and "what should I try deploying for this model/framework/hardware?" It must stay generic to dstack workload prototyping and must not mention endpoint statuses, preset saving, endpoint DB rows, or Claude-specific implementation details. Endpoint-specific requirements stay in `system_prompt.md`.

Recipe grounding should be source-oriented, not a static recipe encyclopedia. The agent should prefer current primary sources such as model cards, vLLM/SGLang docs, dstack docs/CLI help, and its own command/log evidence. Advanced posts such as Wafer GLM-on-AMD and LMSYS agent-assisted SGLang development are directional for future harness work, not v1 requirements.

The prompt interpolates endpoint env keys (names only), ProfileParams constraints, and project context. Recipe grounding is discovered by the agent through allowed network/command facilities and recorded in the final report; do not model it as a required `find_model_recipes` function in v1.

### 8.5 Execution, cost & limits

- Runs inside the pipeline worker (§6.2) unless the chosen runtime forces a detached process model. Agent execution must not block the event loop; use async subprocess/process supervision or a small dedicated executor with bounded concurrency, not the shared 128-thread default executor.
- Between agent/runtime steps, or through runtime cancellation hooks, the service checks `should_abort()` (cheap SELECT of stop intent + `lock_token` sanity) and exits early on stop.
- Do **not** add generic endpoint provisioning timeouts, unused turn counters, or a public agent-budget field in v1. Agent budget/cost governance is Later and must be added only with durable per-session accounting and an actually enforced runtime contract.
- Model via `DSTACK_AGENT_ANTHROPIC_MODEL` if the selected runtime supports explicit model selection (default: `claude-opus-4-8`; the default agent should bias toward the strongest Anthropic model because endpoint provisioning is an expensive, tool-heavy deployment investigation).
- Concurrency bound = pipeline `workers_num` per replica (4).
- Observability: log each command + final summary at INFO with the endpoint id; store command transcripts under the endpoint workspace or log service for debugging; store the final agent summary in `status_message` on failure; store `recipe_sources` in the saved preset comments on success. Cost accounting/events → Later.

---

## 9. Settings, packaging, docs

New in `src/dstack/_internal/server/settings.py` (documented in `mkdocs/docs/reference/env.md`, as the module docstring requires):

| env var | constant | default | notes |
|---|---|---|---|
| `DSTACK_AGENT_ANTHROPIC_API_KEY` | `AGENT_ANTHROPIC_API_KEY` | `None` | as specified by the requirement (agent-scoped, hence no `_SERVER_`); presence ⇒ agent enabled |
| `DSTACK_AGENT_CLAUDE_PATH` | `AGENT_CLAUDE_PATH` | `None` | optional path to the Claude Code executable; falls back to resolving `claude` from `PATH` |
| `DSTACK_AGENT_ANTHROPIC_MODEL` | `AGENT_ANTHROPIC_MODEL` | `claude-opus-4-8` | override only if the operator intentionally wants a cheaper/faster model |

Plain module constants in `settings.py`, not env-configurable in v1: `SERVER_PROJECTS_DIR_PATH = <server dir>/projects`, `ENDPOINT_RUNNING_CHECK_INTERVAL = 60s`.

Packaging: the selected real agent runtime dependency/binary is installed automatically without contaminating the server Python environment and without requiring `uv` at runtime. For Docker this means copying the bundled Claude Code executable into the image at build time. For non-Docker server installs, automatic packaging of the `claude` executable must be solved before the agent path is production-ready. Treat this as a release blocker for enabling the Claude agent path, not as optional docs.

Docs: `mkdocs/docs/reference/dstack.yml/endpoint.md` with `#SCHEMA# dstack._internal.core.models.endpoints.EndpointConfiguration` (processed by `scripts/docs/gen_schema_reference.py`), added to `mkdocs.yml` nav and the `reference/dstack.yml.md` index; env vars in `reference/env.md`; a short concepts page ("Endpoints — experimental") once the feature works end-to-end.

---

## 10. Implementation milestones (each ≈ one PR)

**M1 — resource skeleton (no processing).** `core/models/endpoints.py` + registration in `configurations.py`; `EndpointModel` + migration + events wiring; `EndpointPlan` models with the `none` provisioning branch; `services/endpoints/__init__.py` (create/stop/list/get/get_plan shell, status switch, events); schemas + router + `app.py`; `_endpoints.py` API client group; CLI configurator + `EndpointCommand`. Endpoints can be planned/created and sit SUBMITTED forever. Tests: router CRUD, name uniqueness/reapply semantics, configurator parse, sentinel rejection, plan output for no preset/no agent.
**M2 — pipeline & lifecycle.** `background/pipeline_tasks/endpoints.py` + registration; the full state machine of §6.2 with `AgentService`/`EndpointPresetService` as interfaces with disabled/empty defaults (so: SUBMITTED→FAILED "nothing configured", preset-path run-name conflict detection, RUNNING backing-run liveness through `service_run_id`, simple two-phase server-side stop of the linked service run, and FAILED teardown rule). Tests: fetcher query (sqlite+postgres, lock claims, RUNNING cadence, STOPPING handling), every worker transition with fakes, conflict detection, linked-run cleanup. Do not test name-based adoption as ownership.
**M3 — presets + plan offers.** `presets.py` (`EndpointPresetService`, `LocalDirEndpointPresetService`, project-scoped storage/parsing only under `<server dir>/projects/<project name>/presets`), `endpoint-preset` wrapper parsing (`recipes[*].service` + ordered `validations`), legacy preset conversion, `planning.py` matching via `get_plan` using the endpoint's effective `creation_policy` (default `reuse-or-create`, so elastic fleets are allowed), per-recipe `ServerClientError`/unresolved-env skip, config merge, submission path, `EndpointPlan.provisioning_plan=type:"preset"` only for provisionable recipes with offer summary, save-preset interface + sanitizer/merge. Tests: matching unit tests with testing factories (project/fleet/instance), project isolation, merge semantics, invalid preset files skipped, bad-preset-skip, no-offer preset falls through to agent when policy allows, plan prints selected preset/recipe/offers, secret redaction, atomic write.
**M4 — agent + endpoint logs.** Build on `service_run_id` + `EndpointRunSubmissionModel` so only the latest run serves while submission history is preserved. Continue hardening `ClaudeAgentService` around the v0 Claude Code subprocess runtime: workspace/process handling, scrubbed environment, structured final report artifact, vendored context, `EndpointPlan.provisioning_plan=type:"agent"`, agent settings, automatically installed runtime dependencies, `should_abort`/process cancellation, successful-agent preset save on `RUNNING`, `dstack endpoint logs`, and non-detached endpoint apply following server-side logs/status without attach. Tests should cover real runtime integration boundaries actually used by `ClaudeAgentService`, final-report parsing, runtime availability packaging checks for the `server`/`all` extras, endpoint logs command behavior, apply does not call attach, fake-runtime service integration, and FakeAgentService pipeline integration; mocked network/CLI where possible. Manual e2e: local `uv` server install plus server Docker image both reach the same runtime availability state with only `DSTACK_AGENT_ANTHROPIC_API_KEY` configured.
**M5 — docs & polish.** Reference page, env.md, concepts page, `dstack endpoint` help texts, endpoint plan rendering polish, example presets in docs (not shipped as defaults — §11 Q7), manual e2e runbook (local server + real fleet + one preset + one agent deploy).

---

## 11. Key open questions — with recommended answers

1. **Run naming & history.** Q: how to link endpoint↔run and what happens on retries? **A:** preset-backed services use `<endpoint>-serving` when valid because the server submits them. Agent-backed dstack runs use numbered endpoint submissions (`<endpoint>-1`, `<endpoint>-2`, ...), while the final serving run is linked by reported `run_id`. `service_run_id` is authoritative for the serving run; name lookup is conflict detection only for preset submission and strict submission reconciliation in the agent path. `EndpointRunSubmissionModel(endpoint_id, run_id, submission_num, submitted_at)` records endpoint-submitted run history without coupling `RunModel` to endpoints. Agent retry policy → Later.
2. **Who owns the backing run?** Q: which UserModel submits it (no system user exists)? **A:** the endpoint's creator (`user_id` on the row) — correct attribution in events/quotas; mirror the run router by refreshing the user's server-managed SSH key before `get_plan`/submission if missing. A first-class service account → Later.
3. **Where does the agent execute?** Q: inside the pipeline worker vs a detached task with its own heartbeat bookkeeping? **A:** v0 runs inside the worker `process()` under the Heartbeater lease, with `workers_num=4` as the concurrency bound. Same-host process abort and same-session restart/resume are implemented, which is enough to keep testing the real loop. Multi-host supervision and final handoff recovery remain hardening items.
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

- **Preset sources beyond local dir**: S3, git repo (reuse the `services/templates.py` clone/TTL machinery), HTTP registry; richer validation metadata (version pins, observed offer, benchmark results), signed/curated preset channels; shipping default presets; capacity-aware matching over every recorded validation replica and exact offer identity.
- **Preset update policy**: allow the agent to update/replace an existing learned preset only as a repair path, not as optimization. The harness must first prove that the old preset is not reproducible under the conditions it claimed to support (for example same model family/recipe constraints and compatible tested resource topology, but repeated normal preset-path attempts fail for reasons attributable to the preset rather than transient capacity/no-offers/user constraints). Only then may it save a replacement or new version, with evidence of the failed reproducibility attempt and the newly verified deployment. V1 learned presets stay append-only/no-overwrite until this policy is designed and tested on real failures.
- **Explicit recipe selection**: allow endpoint configs to specify `recipe: <num>` later when a model has multiple learned recipes. V1 does not expose this field; it tries stored recipes in order and uses the first recipe with available offers under the endpoint's effective fleets/profile constraints.
- **Automatic provisioning retry policy**: retry failed provisioning through SUBMITTED, backoff, retry history retention, and distinct submitted run names if preserving failed submissions becomes important.
- **Agent retry policy for RUNNING endpoints**: instead of FAILED on health-check failure, re-invoke the agent to diagnose/redeploy; backoff policy; `retry` ProfileParams semantics for endpoints.
- **Alternative agent runtime** — revisit if the first real runtime cannot meet server requirements for non-interactive execution, packaging, cancellation, workspace/env isolation, artifact capture, and cost accounting.
- **Other `AgentService` implementations** (OpenAI-compatible, Bedrock/Vertex via the SDK's provider clients, self-hosted).
- **Richer service creation**: deepen `dstack-prototyping` through real endpoint-agent traces; richer attach/SSH automation for dev environments; benchmarking before marking an endpoint running; autoscaling/replicas/gateway/domain decisions; quantization variant selection; multi-node deployments; P/D disaggregation and other multi-component serving topologies; advanced SGLang development/deployment harnesses inspired by the 2026-07-02 LMSYS agent-assisted SGLang workflow.
- **Workload-aware optimization**: benchmark and tune endpoints by workload profile (chatbot, RAG, code generation, long-form generation), measuring TTFT, ITL, throughput, end-to-end latency, quality, and cost/token. Product references such as Modal Auto Endpoints, Makora, and Runpod Overdrive are useful directionally, but v1 must stop at verified functional deployment and reproducible preset recipes.
- **In-place update / plan-apply**: server-side endpoint `get_plan`/`apply_plan`, model or config changes via the existing service-run `apply_plan` + rolling deployment machinery, no stop/recreate for simple changes; endpoint row updates protected by a `configuration_version`/deployment guard for multi-server safety.
- **Endpoint-level resources**: optional user-specified resource requirements for endpoint configs. Deferred because replica groups make merge semantics non-trivial. If added, the field must be enforced by preset planning and agent-submitted YAML, must define how it combines with preset/service replica-group resources, and must be reflected in the apply plan without pretending it is final tested hardware.
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
| One-shot stop+delete of runs always raising | endpoint stop remains two-phase stop → wait-until-finished → stopped. The CLI-agent should use normal `dstack stop <run> -y` for ruled-out submitted runs and let run lifecycle handle termination (§2.5, §8.3) |
| GPU-run leaks on terminal FAILED | every FAILED transition issues `stop_runs` for a still non-terminal backing run (§6.2) |
| Transaction/lock corruption submitting backing runs from the worker | fresh `get_session_ctx()` for all runs-service calls; endpoint row writes stay token-guarded; any interim progress update leaves lock columns untouched (§6.1) |
| Prompt injection via fetched recipes → server compromise | command execution runs in an endpoint-scoped workspace with a scrubbed environment; the agent uses normal `dstack` CLI rather than server internals; server secrets/DB/cloud credentials and the agent API key are not exposed to commands (§8.2, 8.3) |
| Agent-learned preset writes resolved secrets to disk | preset sanitizer clears `name`, writes endpoint env as names only, redacts secret-looking values, and tests secret redaction (§7.4) |
| Event-loop starvation from long agent IO | supervise the agent runtime with async subprocess/process APIs or a bounded dedicated executor; never the shared default executor; small `workers_num` |
| `RunStatus.RUNNING` ≠ model ready | endpoint `RUNNING` requires a registered running service replica and `ServiceSpec.model.base_url`; endpoint v1 does not add a parallel health probe (§6.4) |
| `MissingGreenlet` on lazy `project.backends` in the worker | refetch joinedloads chain `project → backends` (§6.1) |
| `register_service` raises synchronously during backing run submission (gateway config issues) | caught as submission failure ⇒ FAILED with message; agent prompt includes gateway context |
| Agent deploys a service without `model:` → no model URL to surface | prompt requires `model:`; agent final verification must use the model endpoint, and server readiness validation refuses to mark the endpoint running unless the backing service exposes `ServiceSpec.model.base_url` (§6.2, §8.3) |
| Task-first degenerates into a batch script | prompt/skill require long-lived interactive probes when attach/SSH is available, and the endpoint agent's local `dstack` wrapper now rejects batch-style probe tasks before submission. Unit coverage verifies rejection of a task that packs host/framework/server/curl checks into `commands` and acceptance of a `sleep infinity` probe task. Live e2e must still prove the agent reacts correctly by attaching/SSHing into the task and promoting a clean service |
| Repeated model downloads because cache mounts are omitted | prompt/skill now require optional instance cache mounts for Hugging Face-style model-serving probes/services when useful, or an explicit artifact explaining why cache mounts do not help for that backend/model. Presets preserve useful `volumes` from the verified service |
| Preset/fleet drift between match and provisioning | matching is advisory; run scheduling is source of truth |
| Agent runtime dependency missing in deployment | selected runtime dependencies are included in normal server install paths and Docker images; release Docker uses `dstack[all]`, staging uses `uv sync --extra all`, and local server installs must not require manual runtime installation (§8.2, 9) |
| Missing migration passes unit tests silently | migration is an explicit M1 review item; postgres-parametrized tests |
