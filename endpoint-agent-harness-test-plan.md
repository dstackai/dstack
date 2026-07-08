# Endpoint Agent Harness Test Plan

This document is for testing the agent harness, not for selling the feature.

The core question is not "can Claude write a service YAML?" The core question is:

> Can the endpoint agent efficiently converge on a verified dstack service for a model, under real
> project capacity and budget constraints, while leaving enough evidence to improve the harness after
> every failure?

If a test does not answer that question, it is not a useful harness test.

## Current Research Baseline

### Agent runtime facts to rely on

- Claude Code print/headless mode supports `--output-format stream-json`, `--json-schema`, `--max-turns`, and `--max-budget-usd`. These are useful facts for later runtime governance, but v1 does not expose an endpoint agent-budget field.
- `--max-budget-usd` caps Claude API spend only. It does not cap GPU spend from dstack runs. Budget/cost governance must be designed later with durable per-session accounting before it becomes user-facing.
- Claude Code plugins/skills are useful for packaging context, but they are not the harness. A plugin can expose skills; it does not give us state, candidate accounting, cleanup, resume, spend tracking, or verification gates.
- Public harness engineering writeups emphasize the same lesson: harness design changes outcomes materially, and useful harnesses rely on traces, self-verification/evaluator separation, context handoff artifacts, and controlled execution loops.

Primary references:

- https://docs.anthropic.com/en/docs/claude-code/cli-reference
- https://code.claude.com/docs/en/headless
- https://code.claude.com/docs/en/plugins-reference
- https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- https://www.anthropic.com/engineering/harness-design-long-running-apps
- https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering
- https://www.langchain.com/blog/the-anatomy-of-an-agent-harness

### Deployment recipe sources to rely on

- vLLM has a model recipe index at `https://recipes.vllm.ai/models.json`; as of this check it returned 263 entries and per-model JSON links.
- SGLang exposes `https://docs.sglang.ai/llms.txt`, including cookbook pages for Qwen3, GLM, Llama, and other families, plus advanced pages such as EPD disaggregation.
- `Qwen/Qwen3-0.6B` has a Hugging Face model card with direct vLLM and SGLang launch examples and OpenAI-compatible curl examples. This makes it a good first real model, because the agent should not need to invent the serving path.
- Advanced writeups such as the LMSYS agent-assisted SGLang development post and Wafer GLM-on-AMD post are not v1 requirements, but they define the direction of the harness: model/framework/hardware-specific experimentation, not a generic YAML generator.

Primary references:

- https://recipes.vllm.ai/models.json
- https://docs.vllm.ai/
- https://docs.sglang.ai/llms.txt
- https://docs.sglang.ai/cookbook/autoregressive/Qwen/Qwen3.md
- https://huggingface.co/Qwen/Qwen3-0.6B
- https://qwen.readthedocs.io/en/latest/deployment/vllm.html
- https://qwen.readthedocs.io/en/latest/deployment/sglang.html
- https://www.lmsys.org/blog/2026-07-02-agent-assisted-sglang-development/
- https://www.wafer.ai/blog/glm52-amd

### Product / benchmark references to learn from

These references should influence harness shape and later evaluation, not v1 feature scope.

- Modal Auto Endpoints frames the product as "one command to a model endpoint" while keeping the generated app/code, GPU selection, regionalization, engine flags, metrics, and benchmark results inspectable. The v1 dstack endpoint agent should copy the inspectability principle, not Modal-specific infrastructure or load tuning.
- Makora frames the frontier as full-stack optimization: orchestration, routing/scheduling, engine tuning, speculative decoding, quantization, kernels, and heterogeneous hardware. This is a useful long-term direction for the agent harness, but most of it is explicitly out of v1.
- Runpod Overdrive's benchmark writeup is useful because it evaluates model serving by workload profile, not just model name. It compares configurations across chatbot, RAG, code-generation, and long-form generation workloads and reports throughput, ITL, TTFT, end-to-end latency, quality, and cost/token. This is Later for endpoint optimization, but v1 artifacts should not make it impossible to add these measurements.

Additional references:

- https://modal.com/blog/introducing-auto-endpoints
- https://www.makora.com/
- https://www.runpod.io/blog/overdrive-benchmarks

## What We Are Actually Testing

The harness has five jobs:

1. Give the agent the right operating context.
2. Bound and observe experiments.
3. Separate candidate execution from final endpoint activation.
4. Preserve evidence for repeatability and improvement.
5. Fail usefully instead of looping or spending blindly.

The v0 loop should be intentionally simple, but it must already exercise these jobs.

## Development Preflight: Separate Backend From Agent

During development, do not use the endpoint agent as the first proof that a backend,
region, instance type, image, SSH path, or fleet/run provisioning path works. Before
asking the agent to spend serious time on a target hardware path, run a small independent
dstack preflight with the same constraints.

This preflight is a development/testing practice, not a production endpoint requirement.
Normal endpoint usage should still allow the agent and/or preset path to provision
through dstack.

Recommended preflight order:

1. Check offers with the same backend/region/instance/max-price/spot constraints.
2. For VM-based backends, optionally create or update a fleet separately and wait until
   it can pre-provision or reuse capacity.
3. For container-based backends such as RunPod and Vast.ai, do not treat fleet creation
   as pre-provisioning. Use a pinned `nodes: 0..1` fleet template or direct run
   constraints, then submit a tiny detached task that forces real provisioning.
4. Submit the tiny task on the target hardware, for example `nvidia-smi` in a CUDA base
   image, with a short `max_duration`.
5. Confirm the run reaches image pull/logs/running or records a concrete provisioning
   failure.
6. If it fails before image pull/logs, diagnose as a dstack/backend issue first: events,
   run JSON, fleet state, native backend state, TCP/SSH, shim/cloud-init where reachable.
7. Record confirmed backend/dstack issues in `endpoint-agent-backend-troubleshooting.md`
   with a minimal reproduction.

Only after this preflight passes should a development run treat agent behavior as the
primary thing under test. This prevents mixing "agent made a poor decision" with "the
selected backend cannot currently provision reachable capacity."

## Harness Components Under Test

### Supervisor

The supervisor is server-side code or a standalone prototype runner that starts the agent process, passes endpoint constraints, streams/traces output, and enforces hard gates.

Required responsibilities:

- create isolated workspace and HOME
- create scoped dstack CLI config
- pass only required env vars
- start Claude Code with structured final report schema
- stream compact endpoint logs
- write full debug trace when debug is enabled
- track candidate run names/ids observed from agent output or final report
- stop active candidates on abort/failure when safe
- reject final success without a verified final service report

### Agent

The agent is allowed to:

- read/write files in the workspace
- use web search/fetch
- use shell commands
- invoke the real `dstack` CLI
- create service/task/dev-environment YAMLs for experiments
- submit detached dstack runs within endpoint constraints
- stop bad candidates

The agent is not allowed to:

- use hidden server APIs
- bypass endpoint profile constraints
- mark the endpoint running without a real model request
- keep multiple GPU candidates running without an explicit reason
- write secrets to YAML, logs, presets, or final reports

### Deterministic Observer

The observer is not an LLM. It reads dstack state, events, logs, and workspace artifacts to decide whether the run satisfied gates.

Required checks:

- every submitted run had a recorded candidate entry
- no active non-final candidate remains after terminal failure
- final run exists and is the required service run
- final service has `model` and model URL
- final verification request is recorded
- endpoint constraints were not violated in previews/submissions
- final preset, if saved, includes final service YAML and replica resource evidence
- task/dev probes used for promotion exercised the intended serving stack, not only host/GPU
  visibility

### Placement/Experiment Observer

For create-recipe e2e runs, the observer must also check that the agent did not
blindly choose the first cheap placement:

- allowed fleets were used for offer inspection; global offers alone are not enough;
- if a broad fleet exposes multiple backends, the agent compared backend/runtime
  characteristics, not just fleet names;
- viable reusable or inspectable placements were identified when present: VM-based,
  SSH, Kubernetes, or any backend/runtime path where tasks/dev environments can reuse
  image/package/model cache or support interactive diagnosis;
- if such a placement was viable under the endpoint constraints, the first paid
  experiment was normally a task or dev-environment style probe, not the final service;
- if the agent chose container-style placement or service-first, `progress.jsonl` contains
  a concrete reason, such as no viable reusable offer,
  constraint violation, insufficient GPU/disk, much higher price, no useful cache
  persistence, or final URL/probe behavior being the only remaining unknown;
- the agent treated hourly price as a constraint, not the objective. A cheaper
  container offer is not automatically better than a slightly more expensive reusable
  placement if the reusable placement can reduce total iteration time, repeated model
  downloads, image churn, or debugging risk;
- the final service was submitted only after the probe removed the main uncertainty, or
  after the agent recorded why a probe would not help.
- task-first is not the same as interactive SSH/dev-environment proof. Record whether the
  agent had attach/SSH/dev-environment available, whether it used it, and why not if it
  skipped it.
- if attach/SSH is available, a probe task should normally stay alive while the agent runs
  inspection commands through attach/SSH. A task that packs all checks into one shell
  command chain is only acceptable for a genuinely one-shot question or unavailable
  attach/SSH.
- a probe is useful only if it reaches the intended recipe evidence: selected image or
  install path, Python/framework runtime, model/auth/cache path when feasible, serving
  command/port, and ideally a local health or model API request. `nvidia-smi` alone is
  host evidence, not service recipe proof.
- for Hugging Face-style model serving, check whether probe and final service YAMLs use
  useful optional instance cache mounts, such as Hugging Face and package caches. If not,
  the agent must explain why repeated downloads/setup are acceptable for that backend and
  model size.
- final service verification remains the success gate. If the final service fails a real
  model request, the correct result is another experiment or terminal failure, not a
  successful final report based on task/dev evidence.

This is not a product rule that forbids container backends. It is a harness test:
when reusable/inspectable placement would make the loop faster or more reliable, the
agent should notice and use it.

Run this as a ladder. First use a cheaper scenario where reusable placement exists
inside a modest budget. Then repeat later with broader/more expensive approved hardware
so the harness is not accidentally tuned only for low-cost small-model cases.

## Required Workspace Artifacts

The agent workspace must contain these files by the end of every attempt. They can be written by the agent, the supervisor, or both, but the deterministic observer must be able to parse them.

### `agent_state.json`

Purpose: current phase and budget/candidate bookkeeping.

Required fields:

```json
{
  "endpoint_name": "qwen-endpoint-agent-smoke",
  "model": "Qwen/Qwen3-0.6B",
  "phase": "research|capacity|experiment|verify|success|failure",
  "max_hourly_price": 0.3,
  "started_at": "ISO-8601",
  "updated_at": "ISO-8601"
}
```

### `sources.jsonl`

Purpose: recipe and hardware grounding.

One JSON object per source:

```json
{
  "url": "https://huggingface.co/Qwen/Qwen3-0.6B",
  "kind": "model-card|framework-doc|recipe|dstack-doc|deployment-report|log-evidence",
  "claim": "HF card provides vLLM and SGLang launch examples for this model",
  "used_for": "serving command selection",
  "confidence": "high|medium|low"
}
```

### Decision Trail

Purpose: make deployment decisions reviewable without forcing the agent to write
separate markdown notes.

Must be visible through `progress.jsonl`, `submissions.jsonl`, `sources.jsonl`,
`verification.json`, and `final_report.json`:

- model size and serving mode
- expected framework
- expected VRAM and disk class
- selected dstack constraints
- why the selected offer/fleet is credible
- why cheaper/other offers were rejected if applicable

### `candidates.jsonl`

Purpose: every spend-capable experiment.

One JSON object per candidate transition:

```json
{
  "candidate": "qwen-endpoint-agent-smoke-serving",
  "kind": "service|task|dev-environment",
  "role": "prototype|final",
  "run_id": null,
  "status": "planned|previewed|submitted|provisioning|running|verified|rejected|stopping|stopped|failed",
  "hourly_price": 0.24,
  "resources": "gpu=RTX2000Ada:16GB disk=100GB",
  "reason": "first final service candidate from HF vLLM recipe",
  "timestamp": "ISO-8601"
}
```

### `commands.jsonl`

Purpose: audit and loop analysis.

One JSON object per command:

```json
{
  "timestamp": "ISO-8601",
  "command": "printf 'n\\n' | dstack apply -f service.dstack.yml --max-price 0.3 --on-demand",
  "exit_code": 0,
  "category": "research|offer|preview|submit|status|events|logs|stop|verify",
  "output_path": "command-output/0004.txt"
}
```

### `verification.json`

Purpose: activation gate.

Required on success:

```json
{
  "run_name": "qwen-endpoint-agent-smoke-serving",
  "model_url": "http://...",
  "request_kind": "openai-chat-completions|openai-responses|custom",
  "request_model": "Qwen/Qwen3-0.6B",
  "status_code": 200,
  "response_excerpt": "The capital of France is Paris.",
  "verified_at": "ISO-8601"
}
```

### `final_report.json`

Purpose: handoff to endpoint worker and preset saving.

This is the existing structured report, but the harness tests should reject shallow reports that do not reference the artifact evidence.

Required on success:

- `success: true`
- final `run_name` or `run_id`
- final `service_yaml`
- `recipe_sources`
- `verification_summary`

Required on failure:

- `success: false`
- `failure_summary`
- link to the last useful evidence: candidate, events, logs, source mismatch, or budget/constraint gate

## Hard Gates

These gates are deliberately strict because they protect money and prevent false RUNNING endpoints.

### Before Any Paid Run

- Endpoint constraints are parsed and rendered.
- Agent has produced at least one source or explicit reason why no external source is needed.
- Hardware reasoning exists.
- `dstack apply` preview was run with the endpoint constraints.
- Preview output does not violate `max_price`, `spot_policy`, backend, region, fleet, instance type, or reuse constraints.
- The user-confirmed hourly budget is still valid.
- For development live tests, the target backend/hardware path passed an independent
  dstack preflight, or the test is explicitly about provisioning-stall recovery.

### While a Candidate Is Running

- At most one GPU candidate is active unless the supervisor has an explicit multi-candidate allowance.
- If provisioning has no meaningful progress after the configured observation window, inspect events before continuing.
- If there are no service logs, inspect events and run JSON before resubmitting.
- If a run is stopped externally or `termination_reason` is `stopped_by_user`, do not resubmit automatically.
- Do not repeat the same YAML/offer/image after a failure without a recorded new hypothesis.

### Before Success

- Final run is the required service run name.
- Final run is a service, not a task or dev environment.
- Final service exposes a model URL.
- Final model request succeeded.
- The request used the requested model name.
- Final YAML is present and does not include secret values.
- Candidate history shows no active leftover GPU runs.

### On Failure

- Stop active endpoint-created GPU candidates when safe.
- Do not save a preset.
- Keep workspace artifacts.
- Failure message in endpoint status must be short.
- Detailed evidence must be in endpoint logs/debug trace/workspace, not stuffed into status events.

## Metrics

Every real run should end with these numbers:

| metric | why it matters |
|---|---|
| time to first valid preview | source + config efficiency |
| time to first paid candidate | whether research is stuck |
| time to first logs | infra vs app debugging |
| time to verified model response | actual endpoint value |
| number of paid candidates | spend efficiency |
| total candidate run minutes | GPU spend exposure |
| agent API spend | Claude budget effectiveness |
| repeated command ratio | loop detection |
| repeated failure ratio | harness quality |
| number of source URLs used | grounding |
| number of source URLs that affected final YAML | real grounding vs noise |
| cleanup completeness | leak prevention |

## Scenario Ladder

Run these in order. Do not skip ahead just because the previous scenario looked boring.

### S0: Offline Harness Contract

Goal: verify artifacts and gates without dstack spend.

Input:

```yaml
type: endpoint
name: qwen-endpoint-contract
model: Qwen/Qwen3-0.6B
preset_policy: create
spot_policy: on-demand
max_price: 0.3
```

Run mode:

- Agent may research and write YAML.
- Agent may run `dstack offer`.
- Agent may run `printf 'n\n' | dstack apply ...`.
- Agent must not run `dstack apply -y`.

Pass:

- Required artifacts exist.
- Preview command uses constraints.
- Final report is failure/blocked due no-submit mode, not success.

Fail:

- Agent submits a run.
- Agent writes shallow artifacts.
- Agent guesses unsupported flags/YAML.

### S1: Impossible Constraints

Goal: no-spend failure on capacity/constraint mismatch.

Input examples:

```yaml
type: endpoint
name: qwen-endpoint-no-offers
model: Qwen/Qwen3-0.6B
preset_policy: create
spot_policy: on-demand
max_price: 0.001
```

Pass:

- No paid run submitted.
- `sources.jsonl`, `progress.jsonl`, and the failure report explain that the model is deployable but constraints block capacity.
- Failure summary is concise.

Fail:

- Agent wastes turns trying random YAML.
- Agent suggests violating max price.

### S2: First Real Happy Path, Tiny Model

Goal: first actual endpoint created and verified.

Candidate model:

- `Qwen/Qwen3-0.6B`

Why this model:

- It is small enough for low-cost GPUs.
- Its model card includes direct vLLM and SGLang launch examples.
- The correct path should be easy enough that failures expose harness issues rather than model complexity.

Initial config:

```yaml
type: endpoint
name: qwen-endpoint-agent-smoke
model: Qwen/Qwen3-0.6B
preset_policy: create
spot_policy: on-demand
max_price: 0.3
```

Current local capacity observation on 2026-07-04:

- `dstack offer --max-price 0.3 --on-demand --gpu 1 --max-offers 20` showed multiple offers, mostly Vast.ai plus one RunPod RTX 2000 Ada.
- The previous Vast.ai RTX 5060 Ti attempt stuck in provisioning without service logs. For the next real run, prefer a more stable/common path even if not the cheapest, and ask before increasing `max_price`.
- The CloudRift RTX4090 path reproduced a backend reachability problem with a separate
  `nvidia-smi` task; do not use that path for judging agent quality until the backend
  issue is understood or resolved.

Expected agent behavior:

- Use HF/Qwen source first.
- Prefer vLLM first unless current evidence suggests SGLang is more reliable for the offer/image.
- Use a common CUDA image or Python install path that matches the chosen framework.
- Submit one final service candidate.
- Poll run JSON, events, and logs.
- Verify via OpenAI-compatible chat completion.
- Save preset after success.

Pass:

- Verified model response.
- One paid candidate or a clearly justified second candidate.
- Candidate stopped/cleaned if replaced.
- Preset saved with final YAML and observed resources.

Fail:

- Agent chooses arbitrary cheapest offer with no reasoning.
- Agent loops on `dstack ps` table parsing.
- Agent resubmits after external stop.
- Agent reports success before model request.

### S3: Happy Path Replay From Learned Preset

Goal: prove the preset created by S2 is actually useful without the agent.

Input:

```yaml
type: endpoint
name: qwen-endpoint-preset-replay
model: Qwen/Qwen3-0.6B
preset_policy: reuse
spot_policy: on-demand
max_price: 0.3
```

Pass:

- Plan finds learned preset.
- Plan shows preset and offers.
- Pipeline creates backing service without invoking agent.
- Service reaches running via normal service readiness.

Fail:

- Preset lacks enough resource information to replay.
- Preset matching ignores no-offer state.
- Agent is invoked despite `preset_policy: reuse`.

### S4: Bad Service YAML Recovery

Goal: test whether the agent can debug its own bad deployment.

Setup options:

- Seed prompt/harness with an intentionally bad first hypothesis, such as wrong port or missing `model`.
- Or choose a framework/image combination likely to fail import.

Pass:

- Agent notices validation/runtime failure from preview/logs.
- Agent records new hypothesis.
- Agent stops/replaces bad candidate.
- Final candidate is verified.

Fail:

- Repeats same apply.
- Treats validation failure as no-offers.
- Leaves failed GPU run active.

### S5: Provisioning Stall Recovery

Goal: reproduce the previous stuck-provisioning failure and ensure the agent does not loop.

Setup:

- Use a backend/offer class known to have a chance of provisioning stalls, or simulate via fake agent/runtime in tests.

Pass:

- Agent polls JSON, then events.
- After bounded no-progress window, agent stops or fails with evidence.
- No resubmission after external stop.

Fail:

- Keeps polling table output.
- Dumps huge offer/event output into endpoint status.
- Resubmits after `stopped_by_user`.

### S6: Env / Gated Model Path

Goal: verify env handling and secret hygiene.

Candidate model:

- A small gated/private HF model if available, or a deliberately missing `HF_TOKEN` scenario.

Pass:

- YAML references `HF_TOKEN` by name only.
- Missing/invalid auth is diagnosed from logs.
- Secret value never appears in YAML, endpoint logs, status message, preset, or trace after redaction.

Fail:

- Agent writes secret value into YAML.
- Agent treats auth as hardware failure.

### S7: Medium Model Hardware Reasoning

Goal: test model/hardware sizing, not just tiny-model happy path.

Candidate models:

- `Qwen/Qwen3-4B`
- `Qwen/Qwen3-8B`

Run only after budget confirmation.

Expected behavior:

- Agent estimates VRAM/disk before offers.
- Agent evaluates quantized variants if needed.
- Agent may choose larger GPU over cheapest if reliability/VRAM requires it.

Pass:

- Reasoning links model size, precision/quantization, max model length, framework, and selected offer.
- Candidate verifies.

Fail:

- Guesses `gpu: 16GB` or `gpu: 80GB` without evidence.
- Confuses parameter size with runtime memory.

### S8: Framework Choice

Goal: verify that the harness supports real vLLM vs SGLang choice.

Input:

- Use a model with both vLLM and SGLang evidence.

Pass:

- Agent records why it chose one framework.
- If first framework fails, switching framework is a new hypothesis with evidence.

Fail:

- Agent always uses one framework regardless of source/log evidence.

### S9: Advanced Scenario, No v1 Implementation

Goal: ensure advanced sources improve planning without causing premature v1 scope explosion.

Candidate sources:

- GLM-on-AMD Wafer post.
- LMSYS agent-assisted SGLang development post.
- SGLang EPD disaggregation docs.

Pass:

- Agent identifies advanced deployment patterns and marks them later unless required.
- No multi-service router/worker topology is attempted in v1 by default.

Fail:

- Agent tries P/D disaggregation for a simple endpoint.
- Agent ignores advanced evidence for a model that actually needs it.

## Real Server Path During Development

Use the actual endpoint worker path for live agent tests. Avoid building a separate
endpoint runner unless there is a specific bug that cannot be isolated through the real
server path, unit tests, workspace artifacts, and the backend preflight above.

Development live-test order:

1. Run the independent dstack/backend preflight for the intended hardware path.
2. Apply the endpoint config through `dstack apply -f <endpoint>.dstack.yml`.
3. Watch endpoint logs and the agent workspace artifacts.
4. Stop candidate runs promptly if the agent stalls or the backend preflight evidence no
   longer matches reality.
5. If the issue is dstack/backend, reproduce it outside endpoints and report it in
   `endpoint-agent-backend-troubleshooting.md`.

For the next probe-path e2e, success is not just "the endpoint eventually runs." The agent must
show the intended loop: submit a long-lived task/dev probe, attach/SSH into it, run real recipe
checks inside the live environment, then promote a clean service and verify that service through
the model API. A batch task that embeds the whole investigation in `commands` is a harness failure.

## Server Integration Gates

Only harden endpoint worker behavior after the real server path or unit tests show it is
needed. Avoid speculative scaffolding.

### Gate A: Runtime

- Claude Code subprocess can run non-interactively from server env.
- Budget/cost governance is deferred until it can be enforced durably per endpoint agent session.
- Stream JSON parsing does not block.
- Large tool outputs are kept out of endpoint status.
- Debug trace captures enough detail.

### Gate B: Candidate Accounting

- Every paid candidate has a recorded candidate row or artifact.
- Latest/final service run is distinguishable from prototypes.
- Deletion/abort stops active candidates.
- Worker crash recovery can reconcile linked/submitted runs.

### Gate C: Verification

- Agent final report alone is not enough.
- Report must reference `verification.json`.
- Server should validate that final run exists and exposes model URL, but the agent owns functional verification.

### Gate D: Preset Save

- Preset is saved only after verified success.
- Preset stores final service YAML and ordered replica resource evidence.
- Preset does not include secrets.
- Replay scenario passes.

## First Real Run Decision

Next paid run should be S2, but only after confirming:

- max hourly price
- acceptable backend/provider preference
- whether to avoid Vast.ai for the next attempt after the prior stuck provisioning
- whether to raise max price for a more stable/common NVIDIA offer

Recommendation:

- Keep `Qwen/Qwen3-0.6B`.
- Keep `preset_policy: create`.
- Keep `spot_policy: on-demand`.
- Consider preferring RunPod or another stable backend if available under budget, even if Vast.ai is cheaper.
- Do not increase `max_price` without explicit confirmation.

## What Counts As Harness Improvement

A change improves the harness only if it moves one of these metrics:

- fewer paid candidates for same scenario
- lower total GPU minutes
- fewer repeated commands/failures
- better diagnosis on failure
- more reliable cleanup
- better source-to-YAML traceability
- higher replay success from learned preset

Prompt wording, skills, plugins, or runtime flags are implementation details. They are only useful if the scenario evidence improves.

## Now vs Later From Product References

### Now

- Keep the "one endpoint config to verified service" UX.
- Make the generated service YAML inspectable and save it as preset provenance.
- Record the engine/framework choice and important serving flags in `sources.jsonl`, `verification.json`, and the final report.
- Record enough final-run metadata to reproduce: model, framework, image/install path, command, resources, observed replica resources, and verification request.
- Treat "no hidden black box" as a v1 principle: if the agent made a deployment decision, the workspace artifacts should show why.
- Keep first verification functional: a real model request proves the endpoint works.

### Later

- Load testing and workload-profile optimization.
- Benchmarking across chatbot/RAG/code/long-form profiles.
- TTFT, ITL, throughput, end-to-end latency, quality, and cost/token dashboards.
- Autoscaling and multi-replica tuning.
- Speculative decoding, quantization strategy exploration, engine patching, kernel work, and heterogeneous hardware optimization.
- Agent retry policy that uses production traffic metrics to re-tune a running endpoint.
- Curated benchmarked presets or a registry that includes measured workload profiles.

### Do Not Do In V1

- Do not ask the agent to optimize under load.
- Do not gate endpoint RUNNING on benchmark performance.
- Do not add generic performance dashboards before basic deployment/replay works.
- Do not let performance references push us into P/D disaggregation, routers/workers, or custom kernels for simple endpoints.
