# Endpoint Agent Checkpoints

This file tracks local endpoint-agent checkpoints: what code version was tested, what
actually worked, how much it cost, and what to improve next. It is intentionally local
and practical, not product documentation.

## Recovery Workflow

Use this branch for experimental endpoint-agent work:

```bash
git switch endpoint-agent-checkpoints
```

Each useful checkpoint should have:

- a git commit
- a local tag named `endpoint-agent/<checkpoint-id>`
- the exact model, endpoint, service run, backend, hardware, and cost
- the focused tests/linters that passed
- links or paths to useful local runtime artifacts
- the main known issues before the next checkpoint

To return to a known-good checkpoint:

```bash
git switch endpoint-agent-checkpoints
git checkout endpoint-agent/<checkpoint-id>
```

For normal development after inspecting an old checkpoint:

```bash
git switch endpoint-agent-checkpoints
```

## Checkpoint: qwen-runpod-v0-running

Status: known-good first real endpoint-agent smoke.

Expected tag after commit:

```bash
endpoint-agent/qwen-runpod-v0-running
```

Date: 2026-07-04
Base branch tip before this work: `be48b560e` (`Fix TestGetRunsTable::test_simple_run (#3999)`)

### What Worked

- Endpoint `qwen-endpoint-happy` reached `running`.
- Model: `Qwen/Qwen3-0.6B`.
- Agent submitted and verified service run `qwen-happy-v2`.
- Final run ID: `b0831bdc-7456-42ab-8c43-ee250427717f`.
- Endpoint URL: `/proxy/services/main/qwen-happy-v2/v1`.
- Backend/hardware: RunPod `CA-MTL-1`, NVIDIA A40 48GB, 9 CPU, 50GB RAM, 60GB disk.
- Hourly price: `$0.44/hr`.
- Reported run cost at checkpoint time: `$0.0599`.
- Service probe had `success_streak: 20`.
- `dstack logs qwen-endpoint-happy --since 1m` resolved through the endpoint name and showed HTTP 200 model requests.
- Preset was saved at:
  `/Users/dstack/.dstack/server/data/endpoint_presets/qwen-qwen3-0-6b-b0831bdc.dstack.yml`.
- Saved preset captured the service YAML plus replica resource evidence for replica group `0`.

### Verification Commands

```bash
uv run dstack endpoint get qwen-endpoint-happy --json
uv run dstack run get qwen-happy-v2 --json
uv run dstack logs qwen-endpoint-happy --since 1m
uv run pytest src/tests/_internal/cli/commands/test_logs.py src/tests/_internal/server/services/endpoints/test_claude_agent.py
uv run pytest src/tests/_internal/cli/commands/test_logs.py src/tests/_internal/cli/services/configurators/test_endpoint.py src/tests/_internal/cli/utils/test_endpoint.py src/tests/_internal/core/models/test_endpoints.py src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py src/tests/_internal/server/routers/test_endpoints.py src/tests/_internal/server/services/endpoints src/tests/_internal/server/services/test_endpoint_presets.py
uv run ruff check src/dstack/_internal/cli/commands/logs.py src/tests/_internal/cli/commands/test_logs.py src/dstack/_internal/server/services/endpoints/agent/claude.py src/tests/_internal/server/services/endpoints/test_claude_agent.py
uv run ruff check $(git diff --cached --name-only -- '*.py')
```

Results observed on 2026-07-04:

- focused pytest: `17 passed`
- broader endpoint pytest: `110 passed, 42 skipped`
- focused ruff: `All checks passed!`
- staged Python ruff: `All checks passed!`
- endpoint status: `running`
- service run status: `running`

### Useful Runtime Artifacts

These are outside the repo and are not part of the commit:

- Final report:
  `/Users/dstack/.dstack/server/data/endpoint_agent_runs/0a17fa5a-da2e-4af7-be12-aeaf6666fc3b/workspace/final_report.json`
- Verification:
  `/Users/dstack/.dstack/server/data/endpoint_agent_runs/0a17fa5a-da2e-4af7-be12-aeaf6666fc3b/workspace/verification.json`
- Saved preset:
  `/Users/dstack/.dstack/server/data/endpoint_presets/qwen-qwen3-0-6b-b0831bdc.dstack.yml`

### Known Issues / Next Hardening

- Server logs can still become noisy when agent output contains large YAML/CLI output.
- Endpoint logs now resolve to the backing service, but debug trace storage and readable
  endpoint-agent logs need more real-run pressure.
- Agent guidance improved after the first run, but the harness still needs repeated
  real examples before we can trust the abstractions.
- CloudRift was excluded from endpoint testing after a separate provisioning failure;
  details are in `endpoint-agent-backend-troubleshooting.md`.
- The current smoke is a single-replica vLLM deployment. Later checkpoints need harder
  models, different hardware, no-offer fallback behavior, and failed-candidate cleanup.

### Scope Notes

This checkpoint should save the code version and the first working evidence. It should
not be treated as v1 quality. The point is to keep a recoverable version while the real
agent loop evolves through repeated tests.

### Post-Checkpoint Cleanup

After the checkpoint commit and tag were created, the live endpoint was deleted to stop
GPU spend:

```bash
uv run dstack endpoint delete qwen-endpoint-happy -y
uv run dstack run get qwen-happy-v2 --json
uv run dstack endpoint get qwen-endpoint-happy --json
```

Observed result on 2026-07-04:

- `dstack endpoint delete qwen-endpoint-happy -y` returned `Endpoint qwen-endpoint-happy deleted`.
- The backing service moved to `terminating`, then `dstack run get qwen-happy-v2 --json`
  returned `Run qwen-happy-v2 not found`.
- `dstack endpoint get qwen-endpoint-happy --json` returned `Endpoint not found`.

### Preset Reuse Preview

After cleanup, `.test-configs/endpoint-agent/qwen-endpoint-happy.dstack.yml` was changed
from `preset_policy: create` to `preset_policy: reuse-or-create` so rerunning the smoke
uses the saved preset first.

Preview command:

```bash
echo n | uv run dstack apply -f .test-configs/endpoint-agent/qwen-endpoint-happy.dstack.yml
```

Observed result on 2026-07-04:

- Matched preset: `qwen-qwen3-0-6b-b0831bdc`.
- Matched preset evidence: one verified RunPod A40 replica.
- Planned resources now come from the preset scheduling requirements, not the exact
  verified instance resources.
- The command exited at the confirmation prompt; no endpoint or GPU run was created.

### Agent Status Message Boundary

Endpoint agent failures now keep endpoint `status_message` compact: agent-originated
errors and failure summaries are collapsed to one line and capped at 500 characters.
Full details remain in the endpoint agent workspace artifacts and endpoint logs.

Verification on 2026-07-04:

```bash
uv run pytest src/tests/_internal/cli/commands/test_logs.py src/tests/_internal/cli/services/configurators/test_endpoint.py src/tests/_internal/cli/utils/test_endpoint.py src/tests/_internal/core/models/test_endpoints.py src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py src/tests/_internal/server/routers/test_endpoints.py src/tests/_internal/server/services/endpoints src/tests/_internal/server/services/test_endpoint_presets.py
uv run ruff check src/dstack/_internal/server/background/pipeline_tasks/endpoints.py src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py
```

Observed result:

- endpoint pytest slice: `112 passed, 44 skipped`
- ruff: `All checks passed!`

### Endpoint Failure Status UX

Endpoint tables now show short failure reasons in the `STATUS` column, similar to
`dstack ps`, instead of always showing only `failed`.

Examples observed locally:

- `no offers` for an agent-confirmed no-offers/no-capacity endpoint
- `agent failed` for failed agent runs without a verified report
- `no agent` when preset creation requires the server agent but the runtime/key is missing

The verbose `ERROR` column still contains the endpoint status message.

Verification on 2026-07-04:

```bash
uv run pytest src/tests/_internal/cli/utils/test_endpoint.py
uv run pytest src/tests/_internal/cli/commands/test_logs.py src/tests/_internal/cli/services/configurators/test_endpoint.py src/tests/_internal/cli/utils/test_endpoint.py src/tests/_internal/core/models/test_endpoints.py src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py src/tests/_internal/server/routers/test_endpoints.py src/tests/_internal/server/services/endpoints src/tests/_internal/server/services/test_endpoint_presets.py
uv run ruff check src/dstack/_internal/cli/utils/endpoint.py src/tests/_internal/cli/utils/test_endpoint.py
uv run dstack endpoint -a
```

Observed result:

- endpoint utility pytest: `14 passed`
- broader endpoint pytest: `116 passed, 44 skipped`
- ruff: `All checks passed!`

### Endpoint Get UX

`dstack endpoint get NAME` now prints a human-readable endpoint detail table by
default. `--json` remains available for scripts and exact API inspection.

This makes failed endpoints easier to inspect without requiring verbose list output
or JSON parsing. List/watch output stays compact and continues to show short failure
reasons in `STATUS`.

Verification on 2026-07-04:

```bash
uv run pytest src/tests/_internal/cli/utils/test_endpoint.py
uv run pytest src/tests/_internal/cli/commands/test_logs.py src/tests/_internal/cli/services/configurators/test_endpoint.py src/tests/_internal/cli/utils/test_endpoint.py src/tests/_internal/core/models/test_endpoints.py src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py src/tests/_internal/server/routers/test_endpoints.py src/tests/_internal/server/services/endpoints src/tests/_internal/server/services/test_endpoint_presets.py
uv run ruff check src/dstack/_internal/cli/commands/endpoint.py src/dstack/_internal/cli/utils/endpoint.py src/tests/_internal/cli/utils/test_endpoint.py
uv run dstack endpoint get qwen-endpoint-no-offers-schema
uv run dstack endpoint get qwen-endpoint-no-offers-schema --json
uv run dstack endpoint get --help
```

Observed result:

- endpoint utility pytest: `15 passed`
- broader endpoint pytest: `117 passed, 44 skipped`
- ruff: `All checks passed!`
- plain `endpoint get` shows Project/User/Endpoint/Model/Status/Run/URL/Created/Error
- JSON output and help output still work

### Endpoint Preset CLI

`dstack endpoint preset` lists endpoint presets saved on the server.
`dstack endpoint preset get MODEL --json` returns the model-level preset, and
`dstack endpoint preset delete MODEL` removes it after confirmation.

This is intentionally limited to list/delete. Creating or updating presets remains part
of the endpoint agent flow, where the agent saves a preset only after verifying the final
service.

Verification on 2026-07-04:

```bash
uv run pytest src/tests/_internal/cli/utils/test_preset.py src/tests/_internal/server/services/test_endpoint_presets.py src/tests/_internal/server/routers/test_endpoints.py
uv run pytest src/tests/_internal/cli/commands/test_logs.py src/tests/_internal/cli/services/configurators/test_endpoint.py src/tests/_internal/cli/utils/test_endpoint.py src/tests/_internal/cli/utils/test_preset.py src/tests/_internal/core/models/test_endpoints.py src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py src/tests/_internal/server/routers/test_endpoints.py src/tests/_internal/server/services/endpoints src/tests/_internal/server/services/test_endpoint_presets.py
uv run ruff check src/dstack/_internal/core/models/endpoint_presets.py src/dstack/_internal/server/services/endpoints/presets.py src/dstack/_internal/server/schemas/endpoint_presets.py src/dstack/api/server/_endpoint_presets.py src/dstack/api/server/__init__.py src/dstack/_internal/server/routers/endpoints.py src/dstack/_internal/cli/utils/preset.py src/dstack/_internal/cli/commands/endpoint.py src/dstack/_internal/cli/services/completion.py src/dstack/_internal/cli/main.py src/tests/_internal/cli/utils/test_preset.py src/tests/_internal/server/services/test_endpoint_presets.py src/tests/_internal/server/routers/test_endpoints.py
uv run dstack endpoint preset --help
uv run dstack endpoint preset
uv run dstack --help
```

Observed result:

- focused preset/router pytest: `38 passed, 11 skipped`
- broader endpoint/preset pytest: `125 passed, 46 skipped`
- ruff: `All checks passed!`
- `dstack endpoint preset` lists the saved Qwen endpoint presets
- endpoint help includes `preset            Manage endpoint presets`

### Endpoint Preset Resource Contract

Endpoint presets now separate scheduling requirements from verified runtime evidence:
recipe `service.resources` is used for service planning and offer matching, while
`validations[*].replicas[*].resources` stores exact resources captured from actual
registered service replicas.

`dstack endpoint preset` now displays one row per recipe, and expands service replica groups with child rows when a recipe has multiple groups. Exact validation resources stay in `get --json`.

Invalid local preset files are skipped for user-facing preset listing and logged server-side with
the preset path and parse/validation error.

Verification on 2026-07-04:

```bash
uv run pytest src/tests/_internal/server/services/test_endpoint_presets.py src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py src/tests/_internal/cli/utils/test_preset.py
uv run pytest src/tests/_internal/cli/commands/test_logs.py src/tests/_internal/cli/services/configurators/test_endpoint.py src/tests/_internal/cli/utils/test_endpoint.py src/tests/_internal/cli/utils/test_preset.py src/tests/_internal/core/models/test_endpoints.py src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py src/tests/_internal/server/routers/test_endpoints.py src/tests/_internal/server/services/endpoints src/tests/_internal/server/services/test_endpoint_presets.py
uv run ruff check src/dstack/_internal/server/services/endpoints/presets.py src/dstack/_internal/server/services/endpoints/preset_building.py src/dstack/_internal/cli/utils/preset.py src/tests/_internal/server/services/test_endpoint_presets.py src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py src/tests/_internal/server/routers/test_endpoints.py src/tests/_internal/cli/utils/test_preset.py
uv run dstack endpoint preset
```

Observed result:

- focused preset/endpoint-worker pytest: `69 passed, 35 skipped`
- broader endpoint pytest: `138 passed, 46 skipped`
- ruff: `All checks passed!`
- `dstack endpoint preset` skips the old loose smoke preset and lists the valid learned preset; the server logs the skipped preset path and validation error

### Endpoint Agent Retest After Deleting Preset

Retest used the current checkout server on `127.0.0.1:3000` with a temporary CLI
home at `/tmp/dstack-endpoint-test-home`; the normal/default CLI config was restored
to `main -> 127.0.0.1:3002`.

Flow observed on 2026-07-04:

- Deleted the existing learned Qwen preset.
- Submitted `qwen-endpoint-smoke` with `backend=runpod`, `spot_policy=on-demand`,
  `max_price=0.5`.
- Agent created real service candidates and handled real RunPod capacity failures:
  `qwen3-06b-smoke` failed on A5000 no-capacity, `qwen3-06b-smoke2` initially retried
  the same no-capacity path, then the agent stopped it and tried `qwen3-06b-l4`.
- `qwen3-06b-l4` first tried L4 and then dstack provisioned A40 in CA-MTL-1 at
  `$0.44/hr`; vLLM served `Qwen/Qwen3-0.6B` and real `/v1/chat/completions`
  requests returned HTTP 200.
- Endpoint reached `running`; learned preset saved as `qwen-qwen3-0-6b-94071a4a`.
- Cleanup completed: endpoint deleted, `qwen3-06b-l4` stopped.

Important harness findings:

- Good: real agent loop works end-to-end through deployment, verification, endpoint
  running state, and preset save.
- Bad: the agent copied offer/workaround hardware into final service scheduling
  requirements (`gpu.name: [L4, A40, RTX3090]`) instead of preserving the broadest
  correct model-derived requirement.
- Bad: the agent's verification/final report said L4, but the actual provisioned
  hardware and saved validation resources were A40. The server-side preset builder used
  actual run state correctly; the agent report was stale/inferred.

Patch made after this run:

- Prompt resources now say to derive scheduling requirements from the model/serving
  method, treat preview offers as availability evidence rather than target hardware,
  avoid pinning concrete GPU/region/instance unless required or explicitly justified,
  and re-read `dstack run get --json` after verification to report actual provisioned
  hardware.

## Checkpoint: qwen-runpod-v1-endpoint-dev-running

Status: known-good endpoint-agent smoke with separate local project and corrected
preset resource contract.

Expected local tag after commit:

```bash
endpoint-agent/qwen-runpod-v1-endpoint-dev-running
```

Date: 2026-07-04
Server: current checkout on `127.0.0.1:3000`
CLI project: `endpoint-dev -> http://127.0.0.1:3000`
Default CLI project preserved: `main -> http://127.0.0.1:3002`

### What Worked

- Endpoint `qwen-endpoint-smoke` reached `running`.
- Model: `Qwen/Qwen3-0.6B`.
- Agent submitted and verified service run `qwen-smoke`.
- Final run ID: `cfef76ab-9ec7-4c41-913b-e9595e2979cd`.
- Endpoint URL: `/proxy/services/endpoint-dev/qwen-smoke/v1`.
- Backend/hardware: RunPod `EU-RO-1`, NVIDIA RTX 2000 Ada Generation
  (`RTX2000Ada:16GB:1`), 6 CPU, 31GB RAM, 100GB disk.
- Hourly price: `$0.24/hr`.
- Agent service YAML used model-derived scheduling requirements:
  `resources.gpu: 16GB..`, not a pinned GPU name, region, or instance type.
- Agent used `vllm serve Qwen/Qwen3-0.6B --port 8000 --max-model-len 8192`.
- dstack service probe reached `success_streak: 4`.
- Agent verified both `/v1/models` and `/v1/chat/completions` through the
  dstack service proxy with HTTP 200.
- Endpoint preset was saved as `qwen-qwen3-0-6b-cfef76ab`.
- Saved preset uses broad scheduling requirements and exact tested resources:
  - scheduling: `cpu=2.. mem=8GB.. disk=100GB.. gpu=16GB..:1..`
  - tested: `cpu=6 mem=31GB disk=100GB gpu=RTX2000Ada:16GB:1`

### Verification Commands

```bash
uv run dstack endpoint --project endpoint-dev get qwen-endpoint-smoke --json
uv run dstack run --project endpoint-dev get qwen-smoke --json
uv run dstack endpoint --project endpoint-dev preset
uv run dstack logs --project endpoint-dev qwen-smoke --since 3m
```

Observed result on 2026-07-04:

- endpoint status: `running`
- backing service status: `running`
- preset listed by `dstack endpoint --project endpoint-dev preset`
- `verification.json` recorded HTTP 200 for `/v1/models` and
  `/v1/chat/completions`
- `final_report.json` recorded actual provisioned hardware from run JSON

### Useful Runtime Artifacts

These are outside the repo and are not part of the checkpoint commit:

- Final report:
  `/Users/dstack/.dstack/server/data/endpoint_agent_runs/bb5846b3-4de1-45fb-896f-eaef5ebd73cf/workspace/final_report.json`
- Verification:
  `/Users/dstack/.dstack/server/data/endpoint_agent_runs/bb5846b3-4de1-45fb-896f-eaef5ebd73cf/workspace/verification.json`
- Saved preset:
  `/Users/dstack/.dstack/server/data/endpoint_presets/qwen-qwen3-0-6b-cfef76ab.dstack.yml`

### Known Issues / Next Hardening

- After agent verification, the endpoint briefly transitions from `prototyping` to
  `provisioning` before `running`. This is confusing; the next patch should avoid
  exposing that intermediate status for agent-verified endpoints.
- The agent still sometimes uses invalid CLI forms first, such as `dstack run list`
  or uppercase backend names. The harness prompt should make the supported command
  surface stricter.
- The agent used a generic run name (`qwen-smoke`). Future prompt/harness rules
  should require useful unique names for candidate runs.
- The agent used shell polling loops without explicit timeouts. Future rules should
  require bounded polling and clear progress notes.
- `dstack logs -d` can expose very verbose shim environment output. Normal endpoint
  logs should become a concise major-event stream written by the agent, while full
  trace/debug artifacts stay in the workspace.
- The endpoint agent trace is useful for debugging, but it is too detailed for normal
  `dstack logs ENDPOINT`. Endpoint logs should contain major realtime events only:
  research/plan summary, candidate submitted, provisioning state, service startup,
  verification success/failure, preset save, and cleanup.

### Post-Checkpoint Patch: Agent Status And Logs

Implemented immediately after tag `endpoint-agent/qwen-runpod-v1-endpoint-dev-running`.
The tag remains the recovery point for the known-good live RunPod smoke; these edits
are the next local branch commit.

Status behavior:

- Agent-created endpoints no longer expose an intermediate `provisioning` state after
  the agent returns a verified service run.
- If the reported service is not yet fully visible as a ready dstack service, the
  endpoint stays `prototyping` with `service_run_id` linked.
- Once the linked service is ready, the worker saves the learned preset and moves the
  endpoint directly from `prototyping` to `running`.
- Preset-based endpoint creation still uses `provisioning`.

Endpoint log behavior:

- Claude stream/tool output is no longer copied to endpoint logs.
- Full agent trace and command output remain in workspace artifacts:
  `trace.jsonl` when debug is enabled, plus `commands.jsonl` and `command-output/`.
- The agent now has a user-facing progress protocol: append concise JSON objects to
  `progress.jsonl`, for example
  `{"phase":"submit","message":"Submitted service candidate"}`.
- The server tails `progress.jsonl` and writes only those major events to the configured
  log service for `dstack logs ENDPOINT`.
- Endpoint logs still include concise start/finish markers for the provisioning agent.

Verification on 2026-07-04:

```bash
uv run pytest src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py src/tests/_internal/server/services/endpoints/test_claude_agent.py
uv run pytest src/tests/_internal/cli/commands/test_logs.py src/tests/_internal/cli/services/configurators/test_endpoint.py src/tests/_internal/cli/utils/test_endpoint.py src/tests/_internal/cli/utils/test_preset.py src/tests/_internal/core/models/test_endpoints.py src/tests/_internal/server/routers/test_endpoints.py src/tests/_internal/server/services/endpoints src/tests/_internal/server/services/test_endpoint_presets.py
uv run ruff check src/dstack/_internal/server/background/pipeline_tasks/endpoints.py src/dstack/_internal/server/services/endpoints/agent/claude.py src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py src/tests/_internal/server/services/endpoints/test_claude_agent.py
uv run ruff format --check src/dstack/_internal/server/background/pipeline_tasks/endpoints.py src/dstack/_internal/server/services/endpoints/agent/claude.py src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py src/tests/_internal/server/services/endpoints/test_claude_agent.py
```

Observed result:

- focused endpoint/agent pytest: `51 passed, 36 skipped`
- broader endpoint/log pytest: `104 passed, 11 skipped`
- ruff: `All checks passed!`
- format check: `4 files already formatted`

## Checkpoint: qwen2-runpod-restart-resource-envelope

Status: known-good same-host restart plus learned-preset resource-envelope validation.

Suggested local tag after the next checkpoint commit:

```bash
endpoint-agent/qwen2-runpod-restart-resource-envelope
```

Date: 2026-07-07
Project: `endpoint-e2e`
Server: current checkout on `127.0.0.1:3000`
Test directory: `/Users/dstack/dstack-endpoints-demo/endpoint-agent-restart`

### What Worked

- Endpoint `qwen2-05b-restart-1110` reached `running`.
- Model: `Qwen/Qwen2-0.5B-Instruct`.
- Server restart during `prototyping` reused the same agent session/workspace and did not start a
  duplicate Claude process.
- Claude submitted and verified service run `qwen2-05b-restart-1110-1`.
- Final run ID: `c1be5e1a-6c49-4ef5-926e-4d2171a03d98`.
- Backend/hardware: RunPod `EU-CZ-1`, NVIDIA RTX 3090 24GB.
- Hourly price: `$0.46/hr`; final run cost after cleanup: `$0.0484`.
- Claude reported agent cost: `$1.1923`.
- Agent verified `/v1/chat/completions` through the dstack proxy with HTTP 200 and response model
  `Qwen/Qwen2-0.5B-Instruct`.
- Endpoint preset was saved as `qwen-qwen2-0-5b-instruct-c1be5e1a`.
- Final service YAML used scheduling resources `gpu: 16GB..24GB:1`, not bare `gpu: 1` and not exact
  RTX 3090 resources.
- Saved preset kept reusable scheduling resources separate from exact tested hardware:
  - scheduling: `cpu=2.. mem=8GB.. disk=30GB.. gpu=16GB..24GB:1`
  - tested: `cpu=32 mem=125GB disk=100GB gpu=RTX3090:24GB:1`
- `dstack endpoint stop qwen2-05b-restart-1110 -y` stopped the endpoint and terminated the backing
  service run.
- A no-cost reuse preview for the same model found offers without Claude, but selected the older
  duplicate preset `qwen-qwen2-0-5b-instruct-532ddf05`, not this checkpoint's new
  `qwen-qwen2-0-5b-instruct-c1be5e1a` preset.

### Useful Runtime Artifacts

- Workspace:
  `/Users/dstack/.dstack/server/data/endpoint_agent_runs/6a9ce2c9-2310-4210-9533-0acf47e49d27/1/workspace`
- Final report:
  `/Users/dstack/.dstack/server/data/endpoint_agent_runs/6a9ce2c9-2310-4210-9533-0acf47e49d27/1/workspace/final_report.json`
- Verification:
  `/Users/dstack/.dstack/server/data/endpoint_agent_runs/6a9ce2c9-2310-4210-9533-0acf47e49d27/1/workspace/verification.json`

### Known Issues / Next Hardening

- Claude first wrote `backend` instead of `backends` and omitted `fleets`; the workspace CLI guard
  caught both before paid submission, but the prompt/skill should reduce this wasted turn.
- Endpoint logs showed Claude assistant stdout even though `progress.jsonl` was clean. Fixed after
  this run: assistant stream text is now trace-only; endpoint logs use `progress.jsonl` and explicit
  server lifecycle messages.
- The run recorded successful CUDA/vLLM/FlashAttention behavior but did not capture direct
  `nvidia-smi` host driver output.
- Duplicate presets for the same model now exist from repeated tests. Keep that inspectable in v1;
  automatic update/repair policy is later, but selection/ranking needs a v1 decision if duplicates
  can change which preset is reused.

### Verification Commands

```bash
uv run pytest src/tests/_internal/server/services/endpoints/test_claude_agent.py
uv run pytest src/tests/_internal/core/models/test_endpoints.py src/tests/_internal/cli/services/configurators/test_endpoint.py src/tests/_internal/server/routers/test_endpoints.py src/tests/_internal/server/services/endpoints/test_claude_agent.py src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py
uv run ruff check .
uv run pyright -p .
```

Observed result after the endpoint-log fix:

- focused agent pytest: `30 passed`
- broader endpoint pytest slice: `124 passed, 72 skipped`
- ruff: `All checks passed!`
- pyright: `0 errors, 0 warnings, 0 informations`

## Checkpoint: qwen25-7b-backend-placement-task-first

Status: known-good backend-placement/task-first validation, with a probe-quality fix applied after
review.

Suggested local tag after the next checkpoint commit:

```bash
endpoint-agent/qwen25-7b-backend-placement-task-first
```

Date: 2026-07-07
Project: `endpoint-agent-reasoning`
Endpoint: `qwen25-7b-placement-choice`
Model: `Qwen/Qwen2.5-7B-Instruct`
Fleet: `reusable-vs-container`

### What Worked

- The allowed fleet exposed cheaper RunPod container offers and a JarvisLabs L4 reusable/inspectable
  offer.
- Claude chose JarvisLabs L4 at `$0.44/hr` over cheaper RunPod offers because it could reuse/inspect
  the instance and keep a warm path for the final service.
- Claude submitted a task first: `qwen25-7b-placement-choice-1`.
- Claude then submitted the final service: `qwen25-7b-placement-choice-2`.
- The service reused the warm JarvisLabs instance and verified:
  - `/v1/models=200`
  - `/v1/chat/completions=200`
  - response model matched `Qwen/Qwen2.5-7B-Instruct`
- Endpoint reached `running`, saved a preset, then was stopped cleanly.
- Temporary fleet was deleted afterward; `dstack fleet --project endpoint-agent-reasoning` showed no
  fleets.

### What Was Not Proven

- The agent did not SSH into the task and did not use a dev environment.
- This proves task-first on reusable backend capacity, not an interactive SSH/dev loop.
- The task probe was too shallow: it observed `nvidia-smi` and driver evidence, but failed on
  `python` missing before proving framework import/runtime/server behavior.

### Fix Applied After Review

- Endpoint system prompt and `skills/dstack-prototyping/SKILL.md` now say that `nvidia-smi` is host
  evidence only.
- A task/dev probe must exercise the intended serving image/runtime/command before it can justify
  promotion.
- Final service verification remains the success gate; if final service verification fails, the
  agent must return to the evidence loop instead of writing success.

### Verification Commands

```bash
uv run pytest src/tests/_internal/server/services/endpoints/test_claude_agent.py -q
uv run pytest src/tests/_internal/server/services/test_endpoint_presets.py src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py src/tests/_internal/server/services/endpoints/test_claude_agent.py -q
```

Observed result:

- focused agent pytest: `31 passed`
- broader endpoint/preset/pipeline pytest: `117 passed, 50 skipped`

## Checkpoint: endpoint-probe-task-shape-guard

Status: structural harness fix after the batch-task failure.

Date: 2026-07-07

### Why

The previous prompt/skill change was not enough by itself. In the next live run, Claude added an
optional Hugging Face cache mount, but still encoded the whole probe as a batch task and chose a
RunPod service-like path. That means the agent understood part of the instruction while still
missing the core shape: a probe task should usually be a live environment the agent can attach/SSH
into, not a one-shot shell script.

### Fix

- The endpoint agent's local `dstack` wrapper now rejects batch-style endpoint probe tasks.
- Allowed task probe shape: a single long-lived idle command such as `sleep infinity`, with checks
  run later through attach/SSH.
- Rejected task probe shape: commands that pack `nvidia-smi`, Python/framework imports, `vllm` /
  `sglang`, server startup, or `curl` probes into the task YAML.
- Services are unaffected; the final endpoint proof is still a verified dstack service.

### Verification Commands

```bash
uv run pytest src/tests/_internal/server/services/endpoints/test_claude_agent.py -q
uv run pytest src/tests/_internal/server/services/test_endpoint_presets.py src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py src/tests/_internal/server/services/endpoints/test_claude_agent.py -q
uv run ruff check src/dstack/_internal/server/services/endpoints/agent/claude.py src/tests/_internal/server/services/endpoints/test_claude_agent.py
```

Observed result:

- focused agent pytest: `33 passed`
- broader endpoint/preset/pipeline pytest: `119 passed, 50 skipped`
- ruff: `All checks passed`

## Checkpoint: qwen25-probe-quality-cached-batch-abort

Status: aborted validation run; confirms cache-mount prompt worked but interactive-probe prompt did
not.

Date: 2026-07-07
Project: `endpoint-agent-reasoning`
Endpoint: `qwen25-probe-quality-2202`
Fleet: `probe-quality-mixed`

### What Improved

- Generated task YAML included an optional Hugging Face instance cache mount:
  `/dstack-cache/huggingface` → `/root/.cache/huggingface`, `optional: true`.
- Planned checks still covered vLLM import, local server start, health, and chat completion.

### What Was Still Wrong

- The probe remained a batch `commands` chain instead of a long-lived task plus attach/SSH
  inspection.
- Claude again wrote `jarvislabs+runpod (container-style)` without stronger backend evidence.
- The actual submitted run landed on RunPod L4, so the placement preference regressed.

### Cleanup

- Endpoint `qwen25-probe-quality-2202`: `stopped`
- Task `qwen25-probe-quality-2202-1`: `terminated`, `termination_reason=terminated_by_user`
- Temporary fleet `probe-quality-mixed`: deleted

### Lesson

Prompt-only enforcement is not enough here. The next useful change should give the agent explicit
server-generated backend/fleet capability context and should consider a pre-submit guard or required
artifact for interactive probes, instead of adding more generic prose.

## Checkpoint: qwen25-probe-quality-service-first-abort

Status: aborted validation run; useful harness failure, not a passing endpoint e2e.

Date: 2026-07-07
Project: `endpoint-agent-reasoning`
Endpoint: `qwen25-probe-quality-2136`
Fleet: `probe-quality-mixed`

### What Happened

- Temporary fleet exposed RunPod A5000/L4/RTX3090 offers and JarvisLabs L4.
- Claude wrote that both RunPod and JarvisLabs were "container-only (no reusable VM/SSH state)".
- Claude skipped the task/dev probe and submitted direct service `qwen25-probe-quality-2136-1`.
- The service landed on RunPod CA-MTL-1 A5000 at `$0.27/hr`.
- We stopped the endpoint because the run no longer tested the probe-quality fix.

### Cleanup

- Endpoint `qwen25-probe-quality-2136`: `stopped`
- Service `qwen25-probe-quality-2136-1`: `terminated`, `termination_reason=terminated_by_user`
- Temporary fleet `probe-quality-mixed`: deleted

### Lesson

The failure happened before probe quality. The agent inferred backend capability from the offer
table, turned uncertainty into "no reusable state", and then optimized back to the cheaper RunPod
service-first path.

Prompt/skill correction after this run:

- Do not infer "container-only" or "no reusable state" from offers alone.
- Fleet state (`nodes: 0..N`, `idle_duration`, idle/running instances) matters.
- If backend reuse/SSH/cache behavior is uncertain, resolve that uncertainty; do not use it as a
  reason to skip a task/dev probe.
- Tiny/well-known model is not enough by itself to skip a probe for a create-recipe endpoint on an
  unverified fleet/backend/runtime path.

## Checkpoint: qwen25-probe-quality-batch-task-abort

Status: aborted validation run; useful harness failure after backend-choice improvement.

Date: 2026-07-07
Project: `endpoint-agent-reasoning`
Endpoint: `qwen25-probe-quality-2152`
Fleet: `probe-quality-mixed`

### What Improved

- Claude chose a task probe instead of service-first.
- The task landed on JarvisLabs `L4-1x` at `$0.44/hr`, despite cheaper RunPod offers.
- The planned checks went beyond host visibility: vLLM/Torch/CUDA import, local server start,
  `/health`, `/v1/models`, and a local chat completion request.

### What Was Still Wrong

- The probe was encoded as one batch `commands` chain instead of a long-lived task plus attach/SSH.
- No instance volumes were configured. Run JSON showed `configuration.volumes=[]`,
  `job_spec.volumes=[]`, and `runtime.volume_names=[]`.
- Claude still used imprecise backend wording: `jarvislabs+runpod (container-style)`.

### Cleanup

- Endpoint `qwen25-probe-quality-2152`: `stopped`
- Task `qwen25-probe-quality-2152-1`: `terminated`, `termination_reason=terminated_by_user`
- Temporary fleet `probe-quality-mixed`: deleted

### Fix Applied After Review

- Endpoint prompt and `skills/dstack-prototyping/SKILL.md` now require long-lived interactive probes
  when attach/SSH is available: keep the probe alive with `sleep infinity` or equivalent, attach/SSH
  into it, and run bounded checks inside the live environment.
- Batch task commands are now explicitly reserved for unavailable attach/SSH or truly one-shot
  checks.
- Prompt/skill now require optional instance cache mounts for Hugging Face-style model caches when
  useful, and require the agent to record why cache mounts were omitted.

### Verification Commands

```bash
uv run pytest src/tests/_internal/server/services/endpoints/test_claude_agent.py -q
uv run pytest src/tests/_internal/server/services/test_endpoint_presets.py src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py src/tests/_internal/server/services/endpoints/test_claude_agent.py -q
```

Observed result:

- focused agent pytest: `31 passed`
- broader endpoint/preset/pipeline pytest: `117 passed, 50 skipped`
