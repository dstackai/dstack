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
max_agent_budget: 3
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

The endpoint stayed in `clauding` after the service was already healthy because the server intentionally waits for the agent's `final_report.json`. In this run:

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

`clauding` can look stuck when the service is already healthy but the agent is still verifying or writing the final report. We need better progress events, not necessarily another status.

The agent still needs much better deployment judgment. The `latest` image failure was caught and recovered from, but the next iterations should make image selection, driver compatibility, model memory sizing, and framework choice more systematic.

The current e2e did not exercise dev-environment based prototyping. That is central to the long-term endpoint idea, especially for harder models, custom recipes, multi-node setups, and performance-sensitive serving.

The current e2e did not test multi-replica services, replica groups, autoscaling, PD disaggregation, gateways, private models, or larger models.

The current e2e did not test server restart while Claude is still running. We have code paths for resuming from workspace artifacts, but this needs a real restart test.

The current e2e did not test multiple server instances with Postgres. The endpoint worker uses the existing lock/pipeline pattern, but the multi-server case still needs an explicit integration test.

The current e2e did not test budget interruption behavior. `max_agent_budget` is passed/configured, but we still need a real test proving accumulated agent spend is tracked per endpoint provisioning attempt and interrupts safely.

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

## Assessment

This was the first meaningful proof that the endpoint idea can work end to end: endpoint config in, real agent work, real service deployed, real model request verified, endpoint running, preset saved.

The biggest result is not that Qwen 0.6B runs. The important result is that the system survived a real failed candidate, recovered through agent reasoning, and produced a verified final service that the server could link and persist.

The biggest remaining risk is still the harness quality. For v1, the server plumbing is useful only if the agent loop becomes strong at model/framework/hardware reasoning, uses dstack efficiently, keeps logs readable, and leaves enough trace evidence to improve each failed run.

## Next Tests

1. Run another small no-preset agent deployment and compare behavior against the first Qwen run.
2. Run a server restart test while the endpoint is still `clauding`.
3. Test endpoint stop while Claude is running and after a candidate run has been submitted.
4. Test budget interruption once spend is persisted per endpoint provisioning attempt.
5. Run a private/Hugging Face gated model test with environment handling.
6. Run a larger common model after confirming budget and hardware.
7. Test one dev-environment prototyping flow where the agent experiments before submitting the final service.
8. Add log/trace redaction tests.
9. Add regression tests for run-name ambiguity, final-report-to-running delay, and preset reuse.
