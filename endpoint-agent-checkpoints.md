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

`dstack preset` now lists endpoint presets saved on the server. `dstack preset list`
is equivalent, and `dstack preset delete NAME` removes a saved endpoint preset after
confirmation.

This is intentionally limited to list/delete. Creating or updating presets remains part
of the endpoint agent flow, where the agent saves a preset only after verifying the final
service.

Verification on 2026-07-04:

```bash
uv run pytest src/tests/_internal/cli/utils/test_preset.py src/tests/_internal/server/services/test_endpoint_presets.py src/tests/_internal/server/routers/test_endpoints.py
uv run pytest src/tests/_internal/cli/commands/test_logs.py src/tests/_internal/cli/services/configurators/test_endpoint.py src/tests/_internal/cli/utils/test_endpoint.py src/tests/_internal/cli/utils/test_preset.py src/tests/_internal/core/models/test_endpoints.py src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py src/tests/_internal/server/routers/test_endpoints.py src/tests/_internal/server/services/endpoints src/tests/_internal/server/services/test_endpoint_presets.py
uv run ruff check src/dstack/_internal/core/models/endpoint_presets.py src/dstack/_internal/server/services/endpoints/presets.py src/dstack/_internal/server/schemas/endpoint_presets.py src/dstack/api/server/_endpoint_presets.py src/dstack/api/server/__init__.py src/dstack/_internal/server/routers/endpoints.py src/dstack/_internal/cli/utils/preset.py src/dstack/_internal/cli/commands/preset.py src/dstack/_internal/cli/services/completion.py src/dstack/_internal/cli/main.py src/tests/_internal/cli/utils/test_preset.py src/tests/_internal/server/services/test_endpoint_presets.py src/tests/_internal/server/routers/test_endpoints.py
uv run dstack preset --help
uv run dstack preset
uv run dstack --help
```

Observed result:

- focused preset/router pytest: `38 passed, 11 skipped`
- broader endpoint/preset pytest: `125 passed, 46 skipped`
- ruff: `All checks passed!`
- `dstack preset` lists the saved Qwen endpoint presets
- top-level help now includes `preset            Manage endpoint presets`

### Endpoint Preset Resource Contract

Endpoint presets now separate scheduling requirements from verified runtime evidence:
`replica_spec_groups[*].resources` is used for service planning and offer matching,
while `replica_spec_groups[*].tested_resources` stores exact resources captured from
actual registered service replicas.

`dstack preset` now displays every actual replica when a preset has multiple replicas, using child rows such as `replica=0` or `group=worker replica=1`, matching the hierarchy used by `dstack ps`. It does not summarize replicas as counts.

Invalid local preset files are skipped for user-facing preset listing and logged server-side with
the preset path and parse/validation error.

Verification on 2026-07-04:

```bash
uv run pytest src/tests/_internal/server/services/test_endpoint_presets.py src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py src/tests/_internal/cli/utils/test_preset.py
uv run pytest src/tests/_internal/cli/commands/test_logs.py src/tests/_internal/cli/services/configurators/test_endpoint.py src/tests/_internal/cli/utils/test_endpoint.py src/tests/_internal/cli/utils/test_preset.py src/tests/_internal/core/models/test_endpoints.py src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py src/tests/_internal/server/routers/test_endpoints.py src/tests/_internal/server/services/endpoints src/tests/_internal/server/services/test_endpoint_presets.py
uv run ruff check src/dstack/_internal/server/services/endpoints/presets.py src/dstack/_internal/server/services/endpoints/preset_building.py src/dstack/_internal/cli/utils/preset.py src/tests/_internal/server/services/test_endpoint_presets.py src/tests/_internal/server/background/pipeline_tasks/test_endpoints.py src/tests/_internal/server/routers/test_endpoints.py src/tests/_internal/cli/utils/test_preset.py
uv run dstack preset
```

Observed result:

- focused preset/endpoint-worker pytest: `69 passed, 35 skipped`
- broader endpoint pytest: `138 passed, 46 skipped`
- ruff: `All checks passed!`
- `dstack preset` skips the old loose smoke preset and lists the valid learned preset; the server logs the skipped preset path and validation error

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
  hardware and saved `tested_resources` were A40. The server-side preset builder used
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
uv run dstack preset --project endpoint-dev
uv run dstack logs --project endpoint-dev qwen-smoke --since 3m
```

Observed result on 2026-07-04:

- endpoint status: `running`
- backing service status: `running`
- preset listed by `dstack preset --project endpoint-dev`
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

- After agent verification, the endpoint briefly transitions from `agenting` to
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
  endpoint stays `agenting` with `service_run_id` linked.
- Once the linked service is ready, the worker saves the learned preset and moves the
  endpoint directly from `agenting` to `running`.
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
