# Endpoint E2E Testing Report

Date: 2026-07-06

## Scope

This report covers the first real endpoint agent e2e test against a local dstack server with a real RunPod-backed service. The goal was not to prove every endpoint feature, but to validate the most important path:

1. Apply an `endpoint` configuration.
2. Let the server start the Claude Code based agent.
3. Let the agent use the real `dstack` CLI to create and debug candidate services.
4. Verify the final model endpoint with a real OpenAI-compatible request.
5. Return a final report to the server.
6. Link the endpoint to the final service run.
7. Save a reusable endpoint preset.
8. Mark the endpoint running.

The test was run outside the repo in `~/dstack-endpoints-demo`.

## Test Environment

Project: `endpoint-e2e`

Endpoint config:

```yaml
type: endpoint
name: qwen-endpoint-e2e

model: Qwen/Qwen3-0.6B

backends:
  - runpod
fleets:
  - endpoint-e2e-runpod
spot_policy: on-demand
max_price: 0.5

preset_policy: create
```

Fleet config:

```yaml
type: fleet
name: endpoint-e2e-runpod

nodes: 0..1

resources:
  gpu: 1
  disk: 100GB..

backends:
  - runpod

spot_policy: on-demand
max_price: 0.5
idle_duration: 5m
```

Final service run:

```text
run name: qwen-endpoint-e2e-2
run id:   ea8597ff-4567-418f-9d60-c620991d79a5
backend:  runpod
region:   EU-RO-1
gpu:      NVIDIA RTX 2000 Ada Generation, 16GB
price:    $0.24/hr
image:    vllm/vllm-openai:v0.11.0
model:    Qwen/Qwen3-0.6B
```

Final endpoint state:

```text
qwen-endpoint-e2e  running  qwen-endpoint-e2e-2
```

Saved preset:

```text
qwen-qwen3-0-6b-ea8597ff
```

Preset path:

```text
~/.dstack/server/projects/endpoint-e2e/presets/qwen-qwen3-0-6b-ea8597ff.dstack.yml
```

## What Worked

The endpoint apply path successfully created an endpoint record and moved it into the server-side background processing loop.

The server started the Claude Code agent from the endpoint worker and passed endpoint/project constraints into the agent context.

The agent used real `dstack` CLI commands, not server helper APIs, to submit candidate services and inspect their state.

The agent recovered from a failed first serving attempt, selected a different image, submitted a second candidate service, waited for it to run, and verified the model endpoint with a real `/v1/chat/completions` request.

The final verification was strong enough for v0: HTTP 200, OpenAI-compatible response shape, non-empty generated content, and response model matching `Qwen/Qwen3-0.6B`.

The server consumed `final_report.json`, found the reported run, verified it was a service owned by the same user/project, linked it through `service_run_id`, saved a preset, and marked the endpoint `running`.

Endpoint logs now show concise agent progress rather than raw service logs for this run:

```text
research: Resuming: prior run qwen-endpoint-e2e-1 failed...
candidate: Submitting service qwen-endpoint-e2e-2...
verification: Verified: real chat completion...
done: Service qwen-endpoint-e2e-2 verified...
```

The saved preset contains both reusable service requirements and actual tested hardware. For this run, reusable requirements are broad enough for matching:

```text
cpu=2.. mem=8GB.. disk=100GB gpu=16GB..:1
```

The preset also stores tested hardware separately:

```text
cpu=6 mem=31GB disk=100GB gpu=RTX2000Ada:16GB:1
```

## What Failed First

The first candidate run used a bad final service image:

```text
vllm/vllm-openai:latest
```

That resolved to a newer vLLM/CUDA stack requiring a newer NVIDIA driver than the RunPod host exposed. The service failed with a driver/runtime mismatch. This was a useful failure: it proved the agent must not blindly use `latest` for final serving images.

The initial agent behavior also used a candidate run name too close to the endpoint name. This caused CLI/log ambiguity and made it harder to distinguish endpoint logs from service logs.

Earlier endpoint logs were too noisy in some cases: large CLI output, service logs, and trace-like content could leak into user-facing endpoint logs. The current run is better, but the logging contract still needs hardening.

The endpoint stayed in `prototyping` after the service was already healthy because the server intentionally waits for the agent's `final_report.json`. In this run:

```text
verification.json   10:07:15
final_report.json   10:07:51
endpoint running    after worker consumed final_report.json
```

This is correct behavior, but the UX needs clearer progress messages between "service is healthy" and "endpoint is running".

## Fixes Made During Testing

Agent prompt now requires candidate service run names to be distinct from the endpoint name. Suggested naming is short attempt-based names such as:

```text
<endpoint-name>-1
<endpoint-name>-2
```

Agent prompt and `dstack-prototyping` skill now warn against unproven `:latest` images for final serving and emphasize image/runtime/driver compatibility.

The backend value passed into the agent prompt was fixed to use normal lowercase values such as `runpod`.

The prompt now tells the agent not to wait only on log text. It should poll structured run state and break on terminal statuses.

The agent flow now asks for normal logs first, using debug logs only when needed.

Endpoint status naming is now `running` for successful endpoints. The early `active` prototype rows are cleaned directly in the local DB; the runtime no longer carries an `active` alias.

Endpoint preset storage was moved under the project-scoped server directory:

```text
~/.dstack/server/projects/<project-name>/presets
```

The preset model was adjusted to separate reusable requirements from tested resources.

Endpoint UX was split from run UX:

- endpoint progress logs use `dstack endpoint logs <name>`;
- endpoint lifecycle stop uses `dstack endpoint stop <name>`;
- endpoint presets use `dstack endpoint preset ...`;
- top-level `dstack logs` and `dstack stop` remain run-only;
- the old top-level `dstack preset` command was removed.

Focused agent tests pass:

```text
uv run pytest src/tests/_internal/server/services/endpoints/test_claude_agent.py
17 passed
```

## Preset Reuse Status

A reuse preview was run with:

```yaml
type: endpoint
name: qwen-endpoint-e2e-reuse

model: Qwen/Qwen3-0.6B

backends:
  - runpod
fleets:
  - endpoint-e2e-runpod
spot_policy: on-demand
max_price: 0.5

preset_policy: reuse
```

The planner did match the saved preset:

```text
Preset  qwen-qwen3-0-6b-ea8597ff
```

But it did not find an available offer while the original service was still using the `nodes: 0..1` fleet:

```text
No matching instance offers available.
```

So preset matching is proven at plan level, but actual second deployment from the saved preset is not yet proven. To test it properly, we should either stop the current endpoint/service first or use a fleet that allows another node.

## Remaining Issues

The agent harness is still early. It completed one real model deployment, but we should not generalize too much from a small Qwen/vLLM case.

Endpoint user logs need a stricter contract. They should contain major agent milestones only. Raw command traces, large YAML, huge offer tables, service logs, debug logs, and sensitive config output must stay out of normal endpoint logs.

The first progress line is still too late. The user should see early progress immediately after the agent starts: what it is checking, what constraints it sees, and whether it is researching, submitting, waiting, or verifying.

`prototyping` can look stuck when the service is already healthy but the agent is still verifying or writing the final report. We need better progress events, not necessarily another status.

The agent still needs much better deployment judgment. The `latest` image failure was caught and recovered from, but the next iterations should make image selection, driver compatibility, model memory sizing, and framework choice more systematic.

The current e2e did not exercise dev-environment based prototyping. That is central to the long-term endpoint idea, especially for harder models, custom recipes, multi-node setups, and performance-sensitive serving.

The current e2e did not test multi-replica services, replica groups, autoscaling, PD disaggregation, gateways, private models, or larger models.

The current e2e did not test server restart while Claude is still running. We have code paths for resuming from workspace artifacts, but this needs a real restart test.

The current e2e did not test multiple server instances with Postgres. The endpoint worker uses the existing lock/pipeline pattern, but the multi-server case still needs an explicit integration test.

The current e2e did not test budget interruption behavior. Agent budget/cost governance is deferred until dstack can persist and enforce spend per endpoint agent session.

Debug traces may still contain sensitive command output if the agent runs unsafe inspection commands. This needs a concrete redaction policy before broader testing.

Cleanup behavior after failed candidate services still needs pressure testing. The agent recovered from `qwen-endpoint-e2e-1`, but cleanup policy for abandoned candidate runs needs to be clear and observable.

## 2026-07-06 Preset Reuse E2E

Goal: reapply the stopped `qwen-endpoint-e2e` endpoint with `preset_policy: reuse` from
`~/dstack-endpoints-demo`, prove that the saved preset can create a new service without Claude, and
verify that endpoint lifecycle stays coherent.

Pre-launch endpoint row:

```text
id:     fa60bac3-bd16-47bf-9c1a-768d5c5025aa
status: stopped
run:    -
```

Pre-launch run state:

```text
qwen-endpoint-e2e-2 is still visible in `dstack ps -v`, but it is stopped.
```

Observation: keeping the stopped service run in normal run history is consistent with run UX, but
endpoint reuse must not treat it as live ownership. The endpoint row is the source of truth for the
current backing service; old stopped runs are history.

Launch result:

```text
Configuration: qwen-endpoint-e2e-reuse-same-name.dstack.yml
Preset:        qwen-qwen3-0-6b-ea8597ff
First offer:   runpod EU-RO-1, NVIDIA RTX 2000 Ada Generation, $0.24/hr
```

Immediate post-launch state:

```text
endpoint id:     fa60bac3-bd16-47bf-9c1a-768d5c5025aa
status:          provisioning
service run:     qwen-endpoint-e2e-serving
service run id:  6a8f5e0a-cca6-4ae9-942b-aa5625d109ef
preset policy:   reuse
```

Observation: terminal reapply reused the same endpoint row and reset `created_at` to the new
submission time. This matches the current "one row per endpoint name" direction. The saved preset
path produced a normal service run without invoking Claude.

Progress at about 50 seconds:

```text
endpoint: provisioning
run:      qwen-endpoint-e2e-serving provisioning
logs:     no endpoint log lines
```

Observation: empty endpoint logs are fine for preset reuse because no agent is involved. The only
UX gap is apply-time feedback while the CLI is detached: users see `provisioning`, but detailed
progress lives in normal run status/events/logs rather than endpoint logs.

Progress at about 2-3 minutes:

```text
instance: runpod EU-RO-1, instance id 4zy2c99vxg9gyl, status BUSY
job:      still PROVISIONING
logs:     service logs empty
```

Observation: offer matching and RunPod instance creation worked. The slow part is after the instance
is available, while the job/service is not yet registered. For real UX, endpoint progress should
distinguish "waiting for capacity", "starting instance", "pulling image", and "waiting for service
probe" when dstack already has those signals.

Progress at about 3-4 minutes:

```text
run:      running
probe:    failing
endpoint: provisioning
logs:     first vLLM startup line appears
```

Observation: the preset path is not marking the endpoint running just because the service process is
running. It waits for the service/probe signal, which is the right minimum behavior for preset reuse.

Final preset-reuse state:

```text
13:42:59  run qwen-endpoint-e2e-serving RUNNING
13:45:24  service replica registered to receive requests
13:45:32  endpoint qwen-endpoint-e2e PROVISIONING -> RUNNING
url:      /proxy/services/endpoint-e2e/qwen-endpoint-e2e-serving/v1
```

Result: preset reuse works end to end. It reused the same endpoint row, created a service from the
saved preset without Claude, waited for the service probe/registration signal, and marked the
endpoint `running` with the service proxy URL.

Observation: the runtime took about five minutes from endpoint apply to endpoint running. Most of
that was normal cold start: RunPod instance provisioning, vLLM image/container startup, model
download, torch compile, CUDA graph capture, and service registration. This is a useful baseline
for future agent/preset comparisons.

Direct endpoint verification:

```text
POST /proxy/services/endpoint-e2e/qwen-endpoint-e2e-serving/v1/chat/completions
status: 200
model:  Qwen/Qwen3-0.6B
```

Observation: the proxy endpoint is usable after endpoint status becomes `running`. The small Qwen
model did not follow an "exactly reply" instruction cleanly because it emitted reasoning text, so
future verification prompts for this model should check API/model correctness and non-empty content
rather than strict literal instruction following.

Stop result:

```text
13:46:42  endpoint marked for stopping
13:46:52  service run RUNNING -> TERMINATING
13:47:06  job TERMINATED and RunPod instance TERMINATED
13:47:18  endpoint STOPPED
```

Result: `dstack endpoint stop` stopped the backing service run, terminated the RunPod instance, and
left the endpoint visible as `stopped`.

Follow-up UX cleanup: stopped endpoints now hide the linked service run in `dstack endpoint` and
`get --json` (`RUN` displays `-`, `run_name` is `null`). The internal `service_run_id` remains in
the database for lifecycle/history purposes, but the user-facing field represents the current live
backing service, not old run history.

## 2026-07-07 Same-Host Restart And Resource Envelope E2E

Goal: validate the latest prompt/session changes on a fresh create-policy RunPod endpoint, including
same-host server restart while Claude is running, final service resource envelope quality, final
report handoff, preset save, and stop cleanup.

Endpoint config:

```yaml
type: endpoint
name: qwen2-05b-restart-1110
model: Qwen/Qwen2-0.5B-Instruct

backends:
  - runpod
fleets:
  - endpoint-e2e-runpod
spot_policy: on-demand
max_price: 0.5

preset_policy: create
```

Workspace:

```text
~/.dstack/server/data/endpoint_agent_runs/6a9ce2c9-2310-4210-9533-0acf47e49d27/1/workspace
```

Server restart result:

```text
endpoint id: 6a9ce2c9-2310-4210-9533-0acf47e49d27
Claude pid before restart: 83844
Claude pid after restart:  83844
duplicate Claude process:  no
endpoint state:            prototyping
session/workspace:         reused
```

This validates the same-host case: restarting the server while Claude was already running did not
create a second agent process or a second agent session.

Final service run:

```text
run name: qwen2-05b-restart-1110-1
run id:   c1be5e1a-6c49-4ef5-926e-4d2171a03d98
backend:  runpod
region:   EU-CZ-1
gpu:      NVIDIA GeForce RTX 3090, 24GB
price:    $0.46/hr
image:    vllm/vllm-openai:v0.24.0
model:    Qwen/Qwen2-0.5B-Instruct
```

The final service YAML used the intended scheduling envelope instead of copying exact hardware:

```yaml
resources:
  gpu: 16GB..24GB:1
  disk: 30GB..
```

The saved preset preserved that distinction:

```text
preset:            qwen-qwen2-0-5b-instruct-c1be5e1a
scheduling:        cpu=2.. mem=8GB.. disk=30GB.. gpu=16GB..24GB:1
validation:        cpu=32 mem=125GB disk=100GB gpu=RTX3090:24GB:1
```

This is the important preset-quality result from the run: reuse planning can stay broad enough to
find equivalent 16-24GB offers, while exact verified placement remains inspectable through
`dstack endpoint preset get --json`.

Verification and handoff:

```text
service running:       09:22 UTC
model API HTTP 200:    09:22:46 UTC
final_report.json:     09:23:24 UTC
endpoint running:      09:23:52 UTC
endpoint URL:          /proxy/services/endpoint-e2e/qwen2-05b-restart-1110-1/v1
```

The endpoint correctly stayed `prototyping` after the service was healthy until the agent produced a
structured verification report. Once Claude exited, the worker consumed the report, linked the
service run, saved the preset, and moved the endpoint to `running`.

Stop cleanup:

```text
endpoint stop requested: 09:24 UTC
service run status:      terminated
termination reason:      stopped_by_user
endpoint status:         stopped
final run cost:          $0.0484
Claude reported cost:    $1.1923
```

The stop path terminated the RunPod service and left the endpoint visible as `stopped`.

Remaining issues from this trace:

- Claude first wrote `backend: [runpod]` instead of `backends: [runpod]`, and initially omitted
  `fleets`; the workspace CLI guard caught both before any paid submission and Claude corrected the
  YAML. The guard worked, but the prompt/skill should still reduce this waste.
- The endpoint log stream still included Claude assistant stdout such as "Let me..." and the final
  markdown summary, even though `progress.jsonl` itself was clean. Fixed after the run: endpoint logs
  now come from `progress.jsonl` and explicit server lifecycle messages only; Claude stdout remains
  in trace/artifacts.
- The agent treated early proxy `404 Service not found` as a retryable registration/startup delay and
  then verified successfully. That behavior was good, but the prompt should keep this tied to run JSON
  and service readiness evidence, not blind retries.
- The report recorded that CUDA/FlashAttention/NCCL initialized successfully, but still did not
  capture a direct `nvidia-smi` host driver string. For presets, this should remain explicit:
  runtime worked; exact host driver was not recorded.
- Another preset for the same model already existed from earlier testing. Duplicate learned recipes
  are acceptable for v1 inspection; v1 selection is intentionally simple and deterministic.

Reuse preview after cleanup:

```text
configuration: qwen2-05b-reuse-1110.dstack.yml
preset_policy: reuse
selected preset: qwen-qwen2-0-5b-instruct-532ddf05
offers: 7 matching RunPod offers, first RTX 2000 Ada at $0.24/hr
submitted: no
```

This proved that a Qwen2 preset is reusable without Claude, but it did **not** prove reuse of the
new `c1be5e1a` preset. The planner selected the older duplicate recipe, whose scheduling resources
are looser (`gpu: 1`, `disk: 100GB`) than the new resource-envelope recipe. That is now accepted v1
behavior: try stored recipes in order and use the first recipe whose normal run plan has available
offers. Automatic ranking/update remains deferred.

## 2026-07-07 Qwen2.5 Preset Reuse And CLI UX Check

Goal: validate the preset-reuse path for the model-level recipe format after the latest CLI/storage
changes, and inspect whether the endpoint/preset tables are understandable during normal use.

Test directory:

```text
~/dstack-endpoints-demo/e2e-2026-07-07
```

Important testing note: running `uv run dstack` from outside the repo can pick up the installed
package version instead of this branch. Use the branch binary for isolated e2e runs:

```text
/Users/dstack/dstack/.venv/bin/dstack ...
```

Endpoint config:

```yaml
type: endpoint
name: qwen25-05b-reuse-check
model: Qwen/Qwen2.5-0.5B-Instruct

preset_policy: reuse
fleets:
  - endpoint-e2e-runpod
backends:
  - runpod
spot_policy: on-demand
max_price: 0.5
```

Plan/preview:

```text
preset: Qwen/Qwen2.5-0.5B-Instruct
recipe: 4a73893b
offers: 5 matching RunPod offers under the endpoint constraints
```

Paid run:

```text
endpoint submitted: 2026-07-07 10:33:46 UTC
service run:        qwen25-05b-reuse-check-serving
actual placement:   runpod CA-MTL-1, NVIDIA RTX A5000 24GB
price:              $0.27/hr
```

The service emitted vLLM startup logs, downloaded and loaded the model, compiled/warmed up, exposed
the OpenAI-compatible API, and served real chat-completion requests. The endpoint stayed
`provisioning` until the existing service probe/registration path passed, then moved to `running`.

Direct endpoint verification:

```text
POST /proxy/services/endpoint-e2e/qwen25-05b-reuse-check-serving/v1/chat/completions
status: 200
model:  Qwen/Qwen2.5-0.5B-Instruct
reply:  non-empty assistant message
```

Stop result:

```text
endpoint status: stopped
service run:     terminated/stopped
active spend:    no live GPU run left
```

What this proves:

- The no-Claude preset-reuse path still works after moving presets to model-level recipes.
- The server waits for real service readiness, not only process startup.
- A learned recipe can plan on one currently available offer and land on another valid offer as
  provider availability changes; the actual placement belongs in run/provisioning history and
  future validation evidence, not in the apply table as a promise.
- Empty endpoint logs for `preset_policy: reuse` are acceptable for now because no agent is running.
  If users need richer preset-path progress later, it should come from server lifecycle events, not
  service stdout.

CLI/storage fixes made after this check:

- `dstack endpoint` now hides the backing service run in the default table and shows `POLICY`.
  The service run remains visible in verbose/detail/JSON output as debugging information.
- Default endpoint listing now behaves like `ps`: show unfinished endpoints; if none exist, show the
  latest finished endpoint.
- `dstack endpoint preset` now groups rows by model and shows only the scheduling GPU by default.
  `-v` shows full service scheduling resources. Child `recipe=0`, `recipe=1`, ... rows appear
  only when a model has multiple recipes. Validation counts were removed from the compact table;
  exact validation evidence remains in `dstack endpoint preset get <model> --json`.
- The agent harness now asks Claude to make final GPU service resources vendor-aware when the
  selected/proven hardware is vendor-specific, e.g. `gpu: nvidia:16GB..24GB:1`. The preset loader
  preserves existing vendorless local recipes instead of rewriting them on read.
- The local preset store now merges duplicate files by model for list/get/planning, and save/delete
  collapse or remove all files for that model. In the live project,
  `dstack endpoint preset get 'Qwen/Qwen2-0.5B-Instruct' --json` now returns both recipe ids
  (`c04afca5`, `79a6b0b7`) consistently with the list output.

Verification after code changes:

```text
endpoint-focused pytest: 185 passed, 72 skipped
focused preset/CLI pytest: 57 passed
ruff: All checks passed
pyright: 0 errors
live endpoint table: default shows NAME/MODEL/STATUS/POLICY/CREATED
live preset table: default shows MODEL/GPU, grouped by model with recipe ordinals only when needed
```

## 2026-07-07 Broad-Fleet Vendor-Aware Harness Check

Goal: remove the RunPod-only test bias, verify that the endpoint does not force a backend, and prove
that new learned recipes can be vendor-aware without mutating older local vendorless recipes.

Test fleet:

```yaml
type: fleet
name: endpoint-e2e-gpu
nodes: 0..1
resources:
  gpu: 1
  disk: 30GB..
backends:
  - lambda
  - verda
  - jarvislabs
  - runpod
spot_policy: auto
max_price: 0.5
idle_duration: 5m
```

Important observation: the fleet was no longer RunPod-only, but the currently available matching
offers under `$0.5/hr` were still all RunPod. Lambda, Verda, JarvisLabs, and Vast.ai returned no
matching GPU offers in this local project even with relaxed price checks. So the agent selecting
RunPod in this test was explained by current capacity/offer reality, not by endpoint config.

Endpoint config:

```yaml
type: endpoint
name: qwen25-broad-fleet
model: Qwen/Qwen2.5-0.5B-Instruct
preset_policy: create
fleets:
  - endpoint-e2e-gpu
spot_policy: auto
max_price: 0.5
```

Result:

```text
service run:      qwen25-broad-fleet-1
run id:           b601b053-0b65-4b88-a1ba-53a4ecd15423
actual placement: runpod EU-RO-1, NVIDIA RTX 2000 Ada 16GB
price:            $0.24/hr
endpoint state:   running, then stopped
```

The agent wrote a clean final service YAML:

```yaml
fleets:
  - endpoint-e2e-gpu
max_price: 0.5
spot_policy: auto
resources:
  gpu: nvidia:16GB..24GB:1
  disk: 30GB..
```

The agent verified the model with a real OpenAI-compatible chat request. The server consumed
`final_report.json`, linked the endpoint to the final service run, saved a new vendor-aware recipe,
and marked the endpoint `running`.

Reuse preview after stopping the live endpoint:

```text
configuration: qwen25-broad-reuse-preview.dstack.yml
preset_policy: reuse
selected model preset: Qwen/Qwen2.5-0.5B-Instruct
selected recipe: 4a73893b
offers: 10 matching RunPod offers, first RTX 2000 Ada at $0.24/hr
submitted: no
```

The preview initially showed no offers while the only `nodes: 0..1` fleet slot was occupied by the
live endpoint. After stopping the endpoint, the same preview showed offers. That behavior is
conventional capacity accounting, not a preset matching bug.

Issues found:

- Endpoint logs were blank for the first ~minute while Claude inspected the workspace/fleet. Normal
  endpoint logs need earlier useful progress, even though debug traces already captured commands.
- Older local same-model recipes remain selectable before newer vendor-aware recipes if they are
  provisionable. That is now the explicit v1 rule: try stored recipes in order and use the first
  recipe whose normal run plan has available offers. Explicit `recipe: <num>` selection is deferred.
- The agent still wrote a slightly stale final image (`vllm/vllm-openai:v0.6.6`) for a tiny model.
  It worked, but image choice needs stronger grounding against current vLLM/SGLang guidance in
  harder scenarios.

Follow-up log-smoke fix:

```text
endpoint: qwen25-log-start-smoke
purpose:  create-policy smoke, stopped before any service submission
result:   endpoint logs showed the server startup progress line and Claude's first progress line
service:  no new service run submitted
```

Normal endpoint logs now get an immediate server-written line when the detached Claude session starts:

```text
Starting endpoint prototyping agent for Qwen/Qwen2.5-0.5B-Instruct. Allowed fleets: endpoint-e2e-gpu. The agent will inspect offers, choose a service recipe, deploy it, and verify the model API before the endpoint becomes running.
```

The prompt now also requires Claude's first workspace action to be a short `progress.jsonl` message
before inspecting state, fleets, offers, recipes, logs, or model docs.

## Assessment

This was the first meaningful proof that the endpoint idea can work end to end: endpoint config in, real agent work, real service deployed, real model request verified, endpoint running, preset saved.

The biggest result is not that Qwen 0.6B runs. The important result is that the system survived a real failed candidate, recovered through agent reasoning, and produced a verified final service that the server could link and persist.

The biggest remaining risk is still the harness quality. For v1, the server plumbing is useful only if the agent loop becomes strong at model/framework/hardware reasoning, uses dstack efficiently, keeps logs readable, and leaves enough trace evidence to improve each failed run.

## Next Tests

1. Reduce the YAML/property waste exposed by the guard (`backend` vs `backends`, omitted `fleets`)
   without weakening the guard.
2. Run existing-fleet scenarios that expose both reusable/inspectable backend placement
   (VM-based, SSH, or Kubernetes) and container-style placement if possible. Start with a cheaper
   scenario, then test broader/more expensive hardware separately after budget approval. Each test
   should verify that the agent compares backend/runtime characteristics inside the allowed fleets,
   treats hourly price as a constraint rather than the objective, prefers the reusable placement when
   viable, starts with a task/dev-style probe when that removes meaningful uncertainty, and records a
   concrete reason if it chooses container placement or service-first.
3. Test private/Hugging Face gated model env handling.
4. Run a larger common model after confirming budget and target hardware.
5. Test multiple server instances with Postgres; same-host restart is now tested, multi-host is not.
6. Add log/trace redaction tests and keep endpoint logs limited to progress-level messages.
7. Add regression tests for final-report-to-running handoff, preset reuse, and cleanup of non-final
   submitted runs after restart.

## 2026-07-07 no-cost recipe-selection check

Regression tests now cover the v1 selection rule directly:

- if the first stored recipe has no available offers and the next recipe does, the second recipe is
  selected and the first is retained as the first unprovisionable match;
- if the first stored recipe has available offers, planning stops there and does not inspect later
  recipes.

Live no-cost preview from `~/dstack-endpoints-demo/e2e-2026-07-07`:

```text
configuration: qwen25-broad-reuse-preview.dstack.yml
project:       endpoint-e2e
preset_policy: reuse
selected model preset: Qwen/Qwen2.5-0.5B-Instruct
selected recipe: 4a73893b
offers:        10 matching offers, first RunPod RTX 2000 Ada at $0.24/hr
submitted:     no
```

The preview was run with `n` at the confirmation prompt, so it did not create an endpoint and did
not invoke Claude. Running the same preview by absolute path from the repo still hits the existing
generic CLI `relative_to(Path.cwd())` path error for configs outside the current directory; that was
observed but intentionally left untouched here.

## 2026-07-07 prompt/guard hardening for YAML constraints

Live traces repeatedly showed Claude confusing service YAML fields with CLI flags, especially
writing singular `backend` or omitting `fleets` and relying on the guard to catch it. The guard
stays as the hard safety net, but the prompt/skill should reduce those failed previews.

Changes made:

- endpoint prompt now explicitly separates plural service YAML fields (`fleets`, `backends`,
  `regions`, `instance_types`) from singular CLI flags (`--fleet`, `--backend`, `--region`,
  `--instance-type`);
- `dstack-prototyping` now repeats that distinction near the fleet-filtered offer guidance and the
  final service promotion checklist;
- workspace CLI guard now returns targeted errors for singular run-config keys such as `fleet` and
  `backend`, before falling through to generic missing-constraint messages.

No paid run was needed for this step. Tests covered prompt inclusion and guard behavior.

## 2026-07-07 no-cost capacity preflight

Current project/fleet state:

```text
project: endpoint-e2e
fleet:   endpoint-e2e-gpu
shape:   nodes 0..1, gpu:1, disk 30GB.., spot auto, max_price $0.5
backends: lambda, verda, jarvislabs, runpod
live instances: none
active endpoints: none
```

The last visible run row was only history:

```text
qwen25-broad-fleet-1: terminated, stopped_by_user, price $0.24/hr
```

Offer checks:

- `endpoint-e2e-gpu` under `$0.5/hr`: RunPod only.
- `endpoint-e2e-gpu` under `$1/hr`: still RunPod only.
- Lambda, Verda, and JarvisLabs through this fleet: no matching offers.
- Nebius is not configured in `~/.dstack/server/config.yml`.

Conclusion: the current project cannot test the desired VM/SSH-capable prototyping path. A paid
agent e2e using the current fleet will most likely be a RunPod/container-backed test again. That is
still useful for checking the prompt/guard fix, but it will not validate dev-environment-style
reuse on a VM fleet.

## 2026-07-07 backend-placement e2e setup

Goal: create a no-spend setup that can actually test whether the agent prefers reusable/inspectable
backend placement and task-first probing when that makes sense. The important distinction is that
fleets define allowed capacity, while backend placement determines the prototyping strategy.

Test directory:

```text
~/dstack-endpoints-demo/backend-placement-2026-07-07
```

Project:

```text
endpoint-agent-reasoning
```

Fleet template applied with `nodes: 0..1`, so no GPU spend was started:

```yaml
type: fleet
name: reusable-vs-container

nodes: 0..1

resources:
  gpu: nvidia:24GB:1
  disk: 100GB..

backends:
  - jarvislabs
  - runpod

spot_policy: auto
max_price: 1.5
idle_duration: 30m
```

Fleet-filtered offers under `$1.5/hr`:

```text
runpod     RTX A5000 24GB   $0.27/hr
runpod     RTX A5000 24GB   $0.27/hr
runpod     L4 24GB          $0.39/hr
jarvislabs L4 24GB          $0.44/hr
runpod     RTX 3090 24GB    $0.46/hr
runpod     RTX PRO 4000     $0.57/hr
```

This is a useful harness test shape: cheaper container-style placements exist, but there is also a
viable JarvisLabs L4 placement inside the same allowed fleet. The next paid endpoint run should
validate whether the agent compares backend/runtime characteristics, treats hourly price as a
constraint rather than the objective, prefers the reusable/inspectable placement when it improves the
total experiment loop, starts with a task/dev-style probe before the final service, and records a
concrete reason if it chooses RunPod or service-first.

Prepared endpoint config:

```yaml
type: endpoint
name: qwen25-7b-placement-choice
model: Qwen/Qwen2.5-7B-Instruct

preset_policy: create
fleets:
  - reusable-vs-container
spot_policy: auto
max_price: 1.5
```

No-spend endpoint preview showed the create-policy agent path and exited at confirmation. The paid
run result is below.

## 2026-07-07 backend-placement / task-first e2e

Endpoint:

```text
project:  endpoint-agent-reasoning
endpoint: qwen25-7b-placement-choice
model:    Qwen/Qwen2.5-7B-Instruct
fleet:    reusable-vs-container
```

Allowed capacity intentionally exposed both cheaper container placement and a reusable/inspectable
VM-style placement:

```text
runpod     RTX A5000 24GB   $0.27/hr
runpod     L4 24GB          $0.39/hr
jarvislabs L4 24GB          $0.44/hr
runpod     RTX 3090 24GB    $0.46/hr
```

Observed agent route:

- Chose JarvisLabs L4 over cheaper RunPod offers because JarvisLabs was reusable/inspectable and
  could keep a warm instance inside the same allowed fleet.
- Submitted a task first: `qwen25-7b-placement-choice-1`.
- Then submitted the final service: `qwen25-7b-placement-choice-2`.
- The service reused the warm JarvisLabs L4 instance and reached `running`.
- Final verification succeeded through the dstack service URL: `/v1/models=200` and
  `/v1/chat/completions=200` for `Qwen/Qwen2.5-7B-Instruct`.
- The endpoint moved to `running`, saved the learned recipe, then was stopped cleanly.
- The temporary fleet was deleted; a later fleet listing for `endpoint-agent-reasoning` showed no
  active fleets.

Final service evidence:

```text
run id:        dbc160ff-8e44-4beb-bdcb-7a294c1a5d44
backend:       jarvislabs
region:        india-noida-01
instance:      L4-1x
gpu:           NVIDIA L4 24GB
driver:        580.126.20
CUDA reported: 13.0
price:         $0.44/hr
image:         vllm/vllm-openai:v0.11.0
```

What this proves:

- The agent can notice a reusable/inspectable backend when a cheaper container backend is also
  available inside the same allowed fleet.
- The agent can choose task-first before the final service.
- A warm reusable instance can reduce the final service placement loop.
- The server correctly waited for the agent's final service verification report before marking the
  endpoint `running`.

What this does not prove:

- It did not use SSH or a dev environment. This proves task-first on a reusable backend, not an
  interactive SSH/dev loop.
- The task probe was too shallow. It successfully observed `nvidia-smi`, host driver, and GPU
  memory, but then failed on `/bin/sh: 1: python: not found`. The agent over-interpreted that as
  full image/runtime compatibility. The final service still proved the endpoint, but the probe did
  not prove framework import, `torch.cuda`, model download, local server start, or local API shape.

Required harness correction from this run:

- A task/dev probe must exercise the intended serving image/runtime/command, not only the host.
- `nvidia-smi` is host evidence, not service recipe evidence.
- If a probe exits before framework/runtime/server checks, it is failed or inconclusive evidence.
- The clean service remains the final authority. If final service verification fails, the agent must
  go back to task/dev or submit a changed service; it must not write success.

## 2026-07-07 probe-quality rerun aborted after service-first decision

Goal: validate the probe-quality prompt fix with a fresh create-policy endpoint.

Project and setup:

```text
project:  endpoint-agent-reasoning
endpoint: qwen25-probe-quality-2136
model:    Qwen/Qwen2.5-0.5B-Instruct
fleet:    probe-quality-mixed
```

The temporary fleet intentionally exposed the same placement tension as the previous validation:

```text
runpod     A5000 24GB   $0.27/hr
runpod     L4 24GB      $0.39/hr
jarvislabs L4 24GB      $0.44/hr
runpod     RTX3090      $0.46/hr
```

What happened:

- Claude saw JarvisLabs and RunPod in the fleet-filtered offers.
- Claude wrote that both backends were "container-only (no reusable VM/SSH state)".
- Based on that claim, it skipped the task/dev probe.
- It selected the cheaper RunPod A5000 and submitted service `qwen25-probe-quality-2136-1`.
- We stopped the endpoint before waiting for service verification because the run no longer tested
  the intended probe-quality fix.

Cleanup:

```text
endpoint: qwen25-probe-quality-2136 stopped
service:  qwen25-probe-quality-2136-1 terminated_by_user
backend:  runpod CA-MTL-1 A5000, $0.27/hr
fleet:    probe-quality-mixed deleted
```

Why this matters:

- The issue was not that Claude failed to run a deep enough task probe; it did not run a probe at
  all.
- The deeper issue is that the harness let Claude infer backend capability from an offer table and
  turn uncertainty into a false statement: "both backends are container-only".
- Once it made that false inference, it optimized back to the cheaper container-style service path.

Fix made after this aborted run:

- Endpoint prompt and `dstack-prototyping` now say not to infer "container-only" or "no reusable
  state" from offers alone.
- Fleet state matters: `nodes: 0..N`, `idle_duration`, or an idle/running instance may keep capacity
  warm for a later task or service.
- If backend reuse/SSH/cache behavior is uncertain, the agent must record uncertainty and choose an
  experiment that can resolve it; it must not treat uncertainty as proof that a task would preserve
  nothing.
- For create-recipe endpoints, "the model is small" or "the framework is common" is not enough to
  skip a task/dev probe on an unverified fleet/backend/runtime path.

## 2026-07-07 probe-quality rerun aborted after batch-style task probe

Goal: rerun the same mixed RunPod/JarvisLabs scenario after the backend-capability prompt fix and
watch whether the agent chooses a reusable/inspectable placement and a meaningful probe.

Project and setup:

```text
project:  endpoint-agent-reasoning
endpoint: qwen25-probe-quality-2152
model:    Qwen/Qwen2.5-0.5B-Instruct
fleet:    probe-quality-mixed
```

Fleet-filtered offers again included cheaper RunPod A5000/L4 options and JarvisLabs L4:

```text
runpod     A5000 24GB   $0.27/hr
runpod     L4 24GB      $0.39/hr
jarvislabs L4 24GB      $0.44/hr
runpod     RTX3090      $0.46/hr
```

What improved:

- Claude did not default back to the cheapest RunPod service.
- Claude submitted a task first: `qwen25-probe-quality-2152-1`.
- The task landed on JarvisLabs `L4-1x` at `$0.44/hr`.
- The intended checks were deeper than `nvidia-smi`: vLLM/Torch/CUDA import, local vLLM server
  start, `/health`, `/v1/models`, and `/v1/chat/completions`.

What was still wrong:

- The task was a batch script, not an interactive probe. The full investigation was encoded into
  one shell command chain instead of starting a long-lived task and attaching/SSH-ing into it.
- The task had no instance cache mounts. Run JSON confirmed:

```text
configuration.volumes=[]
job_spec.volumes=[]
runtime.volume_names=[]
```

- The agent still wrote `jarvislabs+runpod (container-style)` too loosely. It did not use that claim
  to skip the probe this time, but backend capability still needs stronger evidence than names in an
  offer table.

Cleanup:

```text
endpoint: qwen25-probe-quality-2152 stopped
task:     qwen25-probe-quality-2152-1 terminated_by_user
backend:  jarvislabs L4-1x, $0.44/hr
fleet:    probe-quality-mixed deleted
```

Fix made after this run:

- Endpoint prompt and `dstack-prototyping` now say that when SSH/attach is available, a task probe
  should be long-lived (`sleep infinity` or equivalent) and inspected through attach/SSH; batch task
  commands are only for unavailable attach/SSH or truly one-shot checks.
- Prompt/skill now require optional instance cache mounts for Hugging Face-style model caches when
  useful, e.g. `/dstack-cache/huggingface` to `/root/.cache/huggingface` with `optional: true`, and
  they require the agent to record why cache mounts were omitted.

Checks after the fix:

```text
uv run pytest src/tests/_internal/server/services/endpoints/test_claude_agent.py -q
uv run pytest src/tests/_internal/server/services/test_endpoint_presets.py src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py src/tests/_internal/server/services/endpoints/test_claude_agent.py -q
```

Observed result:

```text
31 passed
117 passed, 50 skipped
```

## 2026-07-07 probe-quality rerun aborted after cached batch task

Goal: rerun after the long-lived-interactive-probe and cache-mount prompt update.

Project and setup:

```text
project:  endpoint-agent-reasoning
endpoint: qwen25-probe-quality-2202
model:    Qwen/Qwen2.5-0.5B-Instruct
fleet:    probe-quality-mixed
```

What improved:

- The generated probe task included an optional Hugging Face instance cache mount:

```yaml
volumes:
  - instance_path: /dstack-cache/huggingface
    path: /root/.cache/huggingface
    optional: true
```

- The task again planned recipe-level checks beyond `nvidia-smi`: vLLM import, local vLLM server
  start, health check, and local chat completion.

What was still wrong:

- The task was still a batch `commands` chain, not a long-lived task plus attach/SSH inspection.
- Claude again described `jarvislabs+runpod` as `container-style` based on fleet/offers instead of
  grounded backend capability.
- It selected/submitted RunPod L4 instead of the slightly more expensive JarvisLabs path, so the
  backend-placement behavior regressed from the previous run.
- The run was stopped immediately because it no longer tested the intended interactive probe path.

Cleanup:

```text
endpoint: qwen25-probe-quality-2202 stopped
task:     qwen25-probe-quality-2202-1 terminated_by_user
backend:  runpod NVIDIA L4
fleet:    probe-quality-mixed deleted
```

Conclusion:

Prompt/skill prose is no longer enough for this part of the harness. The next fix should be
structural: pass explicit backend/fleet capability context from the server into the workspace and
consider a pre-submit guard or required pre-submit artifact when the prompt expects an interactive
probe. More wording alone is unlikely to make Claude reliably choose attach/SSH over a batch task.

## 2026-07-07 existing functionality e2e

Goal: before moving to the next endpoint-plan item, re-check the already implemented surfaces
without spending GPU time.

Project state:

```text
project: endpoint-e2e
fleet: endpoint-e2e-gpu active, nodes 0..1, no live instances
unfinished endpoints: none
latest visible run row: qwen25-broad-fleet-1, terminated/stopped_by_user
```

Read-only checks:

- `dstack endpoint --project endpoint-e2e -a -n 10` showed stopped endpoint history and no
  unfinished endpoint.
- `dstack endpoint get qwen25-broad-fleet --json` returned `stopped`, no linked run/url/error.
- `dstack endpoint logs qwen25-broad-fleet --since 24h` showed endpoint progress lines only, not
  backing service logs.
- `dstack endpoint logs qwen25-log-start-smoke --since 24h` showed the server startup line plus
  Claude's first progress line.
- top-level `dstack logs qwen25-broad-fleet` and `dstack stop qwen25-broad-fleet -y` looked for a
  run and returned `Run qwen25-broad-fleet not found`, so endpoint/run command separation holds.
- `dstack endpoint stop qwen25-broad-fleet -y` returned `Endpoint qwen25-broad-fleet is already
  stopped`.

Preset checks:

- compact `dstack endpoint preset list` grouped recipes by model and showed GPU only.
- verbose `dstack endpoint preset list -v` showed full scheduling resources.
- `dstack endpoint preset get Qwen/Qwen2.5-0.5B-Instruct --json` returned both recipes with
  `validations`.
- `dstack endpoint preset get ...` without `--json` correctly refused with `Use --json to output
  the endpoint preset.`

Apply previews, all answered `n`:

- `qwen25-broad-reuse-preview.dstack.yml` selected preset model
  `Qwen/Qwen2.5-0.5B-Instruct`, recipe `4a73893b`, and showed 10 matching RunPod offers.
- `qwen25-broad-fleet-harness.dstack.yml` showed the create/agent path and confirmation without
  submitting.
- `no-fleet-create-preview.dstack.yml` against project `endpoint-agent-choice` showed `The project
  has no fleets. Create one before submitting an endpoint.`
- old `qwen25-05b-create.dstack.yml` correctly showed `No fleets match the endpoint configuration`
  because it still references deleted fleet `endpoint-e2e-runpod`.

Issue found and fixed:

- `dstack endpoint preset list -v` worked, but `dstack endpoint preset -v list` printed compact
  output even though the help shape allowed `-v` before the action. Root cause: the `list`
  subparser's default `verbose=False` overwrote the parent parser's `verbose=True`. Fixed by making
  the child default suppressed; both forms now print verbose output.

Checks run:

```text
uv run pytest src/tests/_internal/cli/commands/test_endpoint.py -q
uv run pytest src/tests/_internal/cli/commands/test_endpoint.py src/tests/_internal/cli/utils/test_preset.py src/tests/_internal/cli/utils/test_endpoint.py src/tests/_internal/cli/services/configurators/test_endpoint.py -q
uv run pytest src/tests/_internal/server/services/test_endpoint_presets.py::TestFindMatchingPreset src/tests/_internal/server/services/endpoints/test_claude_agent.py::TestClaudeAgentService::test_agent_cli_guard_explains_singular_run_config_fields -q
uv run ruff check src/dstack/_internal/cli/commands/endpoint.py src/tests/_internal/cli/commands/test_endpoint.py
```

Result: existing no-spend endpoint functionality looks coherent after the CLI verbose fix. The main
remaining plan work is not basic CLI behavior; it is still the agent/harness durability and richer
real-run scenarios.

## 2026-07-07 main loop validation

Goal: stop polishing peripheral CLI behavior and validate the central loop again:

```text
endpoint config -> Claude deploys and verifies service -> endpoint running -> preset saved -> reuse preview selects the learned recipe
```

Config was kept outside the repo:

```text
~/dstack-endpoints-demo/e2e-2026-07-07/qwen25-mainloop-1642.dstack.yml
```

Endpoint:

```yaml
type: endpoint
name: qwen25-mainloop-1642
model: Qwen/Qwen2.5-0.5B-Instruct
preset_policy: create
fleets:
  - endpoint-e2e-gpu
spot_policy: auto
max_price: 0.5
```

What happened:

- Claude inspected the allowed fleet and current offers, then submitted
  `qwen25-mainloop-1642-1` with `uv pip install vllm`.
- That first service landed on RunPod RTX 2000 Ada at `$0.24/hr`, reached `running`, then failed at
  CUDA initialization. vLLM `0.24.0` pulled a CUDA 13 torch build, while the host driver exposed
  CUDA 12.8 (`found version 12080`).
- Claude diagnosed the failure from service logs, recorded it in endpoint progress, and submitted
  `qwen25-mainloop-1642-2` using
  `vllm/vllm-openai:v0.24.0-cu129-ubuntu2404`.
- The second service reached `running`; `/v1/models` and a real `/v1/chat/completions` request both
  returned HTTP 200 with model `Qwen/Qwen2.5-0.5B-Instruct`.
- The server consumed `final_report.json`, linked endpoint `service_run_id`, set the endpoint to
  `running`, saved the preset, and `dstack endpoint stop` terminated the backing run.

Important harness observations:

- This was a useful real failure: unpinned package installs are risky on container backends because
  host driver/CUDA compatibility is not visible in offers.
- Endpoint progress was substantially better than earlier traces: it showed the failed hypothesis,
  the driver mismatch, the second attempt, and the final verification.
- The official pinned vLLM image avoided the CUDA mismatch, but it also made the provisioning/startup
  phase slower. The agent handled this with bounded polls, though it could still write a progress
  line during long image pulls.
- The final service YAML was vendor-aware (`gpu: nvidia:16GB..24GB:1`) and honored the endpoint
  fleet/price/spot constraints.

Preset reuse issue found and fixed:

- Before the fix, a no-spend `preset_policy: reuse` preview for the same model selected older
  recipe `4a73893b`, not the freshly verified recipe `01141556`.
- Root cause: `save_preset` appended new recipes after older recipes, while v1 planning intentionally
  uses the first provisionable recipe.
- Fix: saving an incoming learned recipe now moves that recipe to the front of the model preset.
  The planner remains simple: first stored recipe with offers wins.
- After re-saving the successful recipe through the preset service, the same no-spend reuse preview
  selected recipe `01141556` and showed matching RunPod offers without invoking Claude.

Checks run:

```text
uv run pytest src/tests/_internal/server/services/test_endpoint_presets.py -q
```

Result: the main loop works for this RunPod/Qwen/vLLM case, including recovery from one real runtime
failure and immediate no-agent preset reuse at the apply-plan level. Next main-path work should focus
on learned recipe quality and more representative scenarios, not more CLI surface polish.

Paid reuse follow-up:

- Submitted `qwen25-reuse-after-mainloop` with `preset_policy: reuse`.
- Apply selected recipe `01141556`, the freshly verified CUDA-12 vLLM image recipe.
- The service run landed on RunPod CA-MTL-1, NVIDIA RTX A5000 24GB, `$0.27/hr`.
- Provisioning looked stuck for several minutes from dstack alone: endpoint/run stayed
  `provisioning` and normal workload logs were initially empty.
- RunPod native REST/GraphQL showed useful intermediate state: the pod was rented, desired status was
  `RUNNING`, runtime/ports existed, image was `vllm/vllm-openai:v0.24.0-cu129-ubuntu2404`, and the
  machine was RTX A5000. The native API did not expose image-pull percentage through the fields used
  here. The HAPI logs URL returned 401/403 with the configured backend API key, so it is not a stable
  backend-diagnostic path for dstack.
- The endpoint then reached `running`, service logs showed vLLM startup and repeated HTTP 200 model
  requests, and `dstack endpoint stop` terminated the backing run cleanly.

Diagnostic lesson: when dstack is stuck at `provisioning` with no workload logs, official native
backend APIs are worth checking for pod/runtime/container state. Do not depend on web-app session
tokens or Clerk endpoints; use the backend's configured API credential and print only sanitized
operational fields.

## 2026-07-07 7B main-loop validation

Goal: validate the central learning loop on a less trivial public model:

```text
endpoint config -> Claude chooses hardware and deploys -> service fails for real reasons ->
Claude adjusts -> service answers model API -> endpoint running -> preset saved -> reuse preview
selects the preset without Claude
```

Config was kept outside the repo:

```text
~/dstack-endpoints-demo/e2e-2026-07-07/qwen25-7b-mainloop-1722.dstack.yml
```

Endpoint:

```yaml
type: endpoint
name: qwen25-7b-mainloop-1722
model: Qwen/Qwen2.5-7B-Instruct
preset_policy: create
fleets:
  - endpoint-e2e-gpu
spot_policy: auto
max_price: 0.5
```

What happened:

- Claude chose a NVIDIA 24GB..48GB envelope for the 7B model, avoiding the earlier too-loose
  `gpu: 1` pattern.
- Run `qwen25-7b-mainloop-1722-1` failed before capacity with `failed_to_start_due_to_no_capacity`.
- Run `qwen25-7b-mainloop-1722-2` landed on RunPod A40 and then failed because FlashInfer tried
  runtime JIT through `/usr/local/cuda/bin/nvcc`, which was not present.
- Run `qwen25-7b-mainloop-1722-3` switched to `vllm/vllm-openai:v0.24.0`, landed on RunPod
  CA-MTL-1 NVIDIA RTX A5000 at `$0.27/hr`, and served the model successfully.
- Final verification used the model endpoint, not service status alone: `/v1/models` returned
  `Qwen/Qwen2.5-7B-Instruct` with `max_model_len: 32768`, and `/v1/chat/completions` returned
  HTTP 200 with content `dstack verification OK`.
- The endpoint moved to `running`, linked `qwen25-7b-mainloop-1722-3`, saved a project-scoped
  preset, and was stopped afterward to cap spend. The backing run is terminated.

Saved preset:

```text
path:      ~/.dstack/server/projects/endpoint-e2e/presets/qwen-qwen2-5-7b-instruct.dstack.yml
recipe:    cb373545
scheduling cpu=2.. mem=8GB.. disk=100GB.. gpu=nvidia:24GB..48GB:1
tested:    cpu=9 mem=50GB disk=100GB gpu=A5000:24GB:1
image:     vllm/vllm-openai:v0.24.0
```

No-spend reuse preview:

```text
config:    qwen25-7b-reuse-preview.dstack.yml
policy:    reuse
selected:  Qwen/Qwen2.5-7B-Instruct recipe cb373545
offers:    12 matching offers under endpoint-e2e-gpu / max_price $0.5
submitted: no
```

Important observations:

- The agent made a reasonable hardware decision for a 7B model and preserved the broad scheduling
  envelope separately from exact A5000 validation hardware.
- The loop recovered from both no-capacity and a concrete runtime/JIT failure without server-side
  special cases.
- The first full service attempt still installed/used a runtime path that led to avoidable JIT
  friction. For vLLM OpenAI services, the prompt/skill should bias toward pinned official vLLM
  serving images unless there is a specific reason to prototype package installation.
- The endpoint worker correctly waited for the agent's functional verification report before
  marking the endpoint running.
- Reuse planning is proven for this learned 7B preset; paid reuse deployment was not submitted in
  this step.

## 2026-07-07 Qwen3.6-27B main-loop validation

Goal: push the learning loop beyond small Qwen models and verify that the agent can use current
recipe sources, choose a defensible 80GB single-GPU shape, wait through a long model startup, perform
real model API verification, and save a reusable recipe.

Config was kept outside the repo:

```text
~/dstack-endpoints-demo/qwen27-2026-07-07/qwen36-27b-create.dstack.yml
```

Endpoint:

```yaml
type: endpoint
name: qwen36-27b-mainloop
model: Qwen/Qwen3.6-27B

preset_policy: create
fleets:
  - qwen27-runpod-a100
spot_policy: auto
max_price: 1.6
```

Result:

- Endpoint reached `running`.
- Final service run: `qwen36-27b-mainloop-1`.
- Run id: `34ed301f-f1f3-4f8d-bebc-5ecae99568b6`.
- Backend/hardware: RunPod `CA-MTL-3`, NVIDIA A100 80GB PCIe, 31 CPU, 117GB RAM, 200GB disk.
- Price: `$1.39/hr`, within endpoint `max_price: 1.6`.
- Image: `vllm/vllm-openai:v0.24.0`.
- Service resource envelope saved in the recipe: `gpu: nvidia:80GB:1`, `disk: 200GB`.
- Preset list now shows model `Qwen/Qwen3.6-27B` with GPU `nvidia:80GB:1`.
- The endpoint was stopped after verification to cap spend; the backing run terminated cleanly with
  final observed cost about `$0.3233`.

Agent evidence:

- Read Hugging Face config and vLLM recipe sources for the exact model.
- Identified `Qwen3_5ForConditionalGeneration`, BF16, hybrid GDN linear-attention + full-attention,
  multimodal vision encoder, and the official vLLM recipe floor.
- Chose BF16 TP1 on 80GB instead of FP8/NVFP4 because the allowed fleet was A100 and the recipe's
  FP8/NVFP4 paths are not the right Ampere assumption.
- Submitted the service directly and recorded why: RunPod is container-style, a task probe would not
  reliably preserve the 50GB+ model download for the final service, and the main remaining unknowns
  were visible in service startup logs.
- Waited through weight download, model loading, torch compile, warmup, CUDA graph capture, API server
  startup, and dstack service probe success.
- Verified the model through the OpenAI-compatible chat API. The successful request returned HTTP 200,
  response model `Qwen/Qwen3.6-27B`, `finish_reason=stop`, and content
  `The capital of France is Paris.`

Runtime evidence from logs and verification artifacts:

- Weight download took about 129 seconds.
- Model loading took 51.1 GiB GPU memory.
- Available KV cache was 18.56 GiB, with 281,804 KV-cache tokens and reported maximum concurrency
  8.60x at 32,768 tokens.
- vLLM used Triton/FLA GDN linear-attention, FlashAttention v2, and FlashInfer sampling without CUDA
  or OOM errors.

Harness observations:

- The `progress` helper materially improved endpoint logs. The user can now see recipe/hardware
  reasoning, why service-first was chosen, when the run landed capacity, when model loading passed,
  when API verification started, and when the final report was written.
- The prompt is still long, but the agent followed the core constraints: existing fleet only,
  endpoint run names as `<endpoint-name>-<submission-number>`, final functional verification, and
  project-scoped preset save.
- One artifact-writing bug appeared: the final report text had `.39/hr` instead of `$1.39/hr` because
  the agent wrote JSON via an unquoted shell heredoc, allowing shell expansion of `$1`. The prompt and
  `dstack-prototyping` skill now require Python serializers or quoted heredocs such as `<<'EOF'` for
  artifacts.
- The agent still used `head -c` once during source inspection despite the prompt. It did not break
  the run, but the harness should continue pushing source inspection toward parsed/bounded fields.
- This run does not prove the task/dev-environment-first path because the allowed fleet was
  container-style RunPod. We still need a VM/SSH-fleet scenario where a task or interactive experiment
  should clearly be cheaper and more informative than repeated services.

No-spend reuse preview after stopping:

```text
config:    qwen36-27b-reuse-preview.dstack.yml
policy:    reuse
selected:  Qwen/Qwen3.6-27B recipe 4a0dd437
offers:    14 matching RunPod A100 80GB offers under qwen27-runpod-a100 / max_price $1.6
submitted: no
```

Checks run after the prompt/skill updates:

```text
uv run pytest src/tests/_internal/server/services/endpoints/test_claude_agent.py -q
```

Result:

```text
31 passed
```

## Probe Task Shape Guard

The `qwen25-probe-quality-*` live tests showed that prompt wording alone did not reliably produce
the intended interactive task path. One run skipped the task and optimized back to RunPod service
first; the next selected a task and JarvisLabs, but encoded the entire serving investigation as one
batch command. That proved the useful next fix was not more prose, but a structural guard.

Implemented guard:

- Endpoint agent task probes must be long-lived attach/SSH targets, normally `commands:
  [sleep infinity]`.
- The wrapper rejects batch probe commands that contain the serving investigation inside task YAML:
  host checks, Python/framework imports, vLLM/SGLang startup, or curl/API probes.
- The agent should run those checks after attaching/SSHing into the live task.

Checks after the guard:

```text
uv run pytest src/tests/_internal/server/services/endpoints/test_claude_agent.py -q
33 passed

uv run pytest src/tests/_internal/server/services/test_endpoint_presets.py src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py src/tests/_internal/server/services/endpoints/test_claude_agent.py -q
119 passed, 50 skipped

uv run ruff check src/dstack/_internal/server/services/endpoints/agent/claude.py src/tests/_internal/server/services/endpoints/test_claude_agent.py
All checks passed
```

Next live e2e should specifically check whether Claude reacts to the wrapper correction by creating
a long-lived task, attaching/SSHing into it, running real serving checks inside, and only then
promoting a clean service.

## Backend Docs Gate And Endpoint Log Watch

Config:

```text
project: endpoint-agent-reasoning
config:  qwen25-docs-gate-e2e.dstack.yml
model:   Qwen/Qwen2.5-0.5B-Instruct
fleet:   probe-quality-guard
policy:  create
```

Result:

- Claude classified backends against `https://dstack.ai/docs/concepts/backends.md`, chose JarvisLabs
  as VM-based, and rejected RunPod as container-based/no instance volumes.
- The task config used `commands: [sleep infinity]`, `fleets: [probe-quality-guard]`,
  `backends: [jarvislabs]`, `gpu: nvidia:16GB..`, and optional Hugging Face instance cache.
- Claude attached/SSHed into the task, started vLLM inside it, and verified a local
  `/v1/chat/completions` request.
- Claude stopped the task, waited for the instance to become idle, submitted the same recipe as a
  service on JarvisLabs, and verified `/v1/chat/completions` through the dstack service URL.
- The endpoint reached `running`, linked `qwen25-docs-gate-e2e-2`, wrote a schema-clean
  `final_report.json`, and was then stopped cleanly.

CLI/log UX change validated by this run:

- `dstack endpoint logs -w` was added.
- Foreground endpoint apply now polls endpoint status and streams the same endpoint progress log
  stream without using `attach`.
- Endpoint logs print local timestamps because they are progress events, unlike raw streamed run logs.
- Endpoint log following uses an overlap plus duplicate counts, so records sharing the same
  timestamp are not swallowed at poll boundaries.

Checks:

```text
uv run pytest src/tests/_internal/cli/commands/test_endpoint.py src/tests/_internal/cli/services/configurators/test_endpoint.py src/tests/_internal/server/services/endpoints/test_claude_agent.py -q
42 passed

uv run ruff check src/dstack/_internal/cli/commands/endpoint.py src/dstack/_internal/cli/services/configurators/endpoint.py src/dstack/_internal/cli/services/endpoint_logs.py src/tests/_internal/cli/commands/test_endpoint.py
All checks passed
```

Remaining issue:

- Endpoint logs are now much more useful, but the first `dstack apply` in this run was started
  before the foreground-log-streaming CLI change, so the new attached-apply UX still needs a direct
  fresh smoke after this patch.
