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

- The endpoint service `qwen-happy-v2` may still be running and spending `$0.44/hr`.
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
