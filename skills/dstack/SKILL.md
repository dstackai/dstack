---
name: dstack
description: |
  dstack is an open-source control plane for GPU provisioning and orchestration across GPU clouds, Kubernetes, and on-prem clusters.
---

# dstack

## Overview

`dstack` provisions and orchestrates workloads across GPU clouds, Kubernetes, and on-prem via fleets.

**When to use this skill:**
- Running or managing dev environments, tasks, or services on dstack
- Creating, editing, or applying `*.dstack.yml` configurations
- Managing fleets, volumes, and resource availability

## How it works

`dstack` operates through three core components:

1. `dstack` server - Can run locally, remotely, or via dstack Sky (managed)
2. `dstack` CLI - Applies configurations and manages resources; the CLI can be pointed to a server and default project (`~/.dstack/config.yml` or via `dstack project`)
3. `dstack` configuration files - YAML files ending with `.dstack.yml`

`dstack apply` plans, provisions cloud resources, and schedules containers/runners. By default it attaches when the run reaches `running` (opens SSH tunnel, forwards ports, streams logs). With `-d`, it submits and exits.

## Quick agent flow (detached runs)

1) Show plan: `echo "n" | dstack apply -f <config>`
2) If plan is OK and user confirms, apply detached: `dstack apply -f <config> -y -d`
3) Check status once: `dstack ps -v`
4) If dev-environment or task with ports and running: attach to surface IDE link/ports/SSH alias (agent runs attach in background); ask to open link
5) If attach fails in sandbox: request escalation; if not approved, ask the user to run `dstack attach` locally and share the output

**CRITICAL: Never propose `dstack` CLI commands or YAML syntaxes that don't exist.**
- Only use CLI commands and YAML syntax documented here or verified via `--help`
- If uncertain about a command or its syntax, check the links or use `--help`

**NEVER do the following:**
- Invent CLI flags not documented here or shown in `--help`
- Guess YAML property names - verify in configuration reference links
- Run `dstack apply` for runs without `-d` in automated contexts (blocks indefinitely)
- Retry failed commands without addressing the underlying error
- Summarize or reformat tabular CLI output - show it as-is
- Use `echo "y" |` when `-y` flag is available
- Assume a command succeeded without checking output for errors

## Agent execution guidelines

### Output accuracy
- **NEVER reformat, summarize, or paraphrase CLI output.** Display tables, status output, and error messages exactly as returned.
- When showing command results, use code blocks to preserve formatting.
- If output is truncated due to length, indicate this clearly (e.g., "Output truncated. Full output shows X entries.").

### Verification before execution
- **When uncertain about any CLI flag or YAML property, run `dstack <command> --help` first.**
- Never guess or invent flags. Example verification commands:
  ```bash
  dstack --help                               # List all commands
  dstack apply --help <configuration type>    # Flags for apply per configuration type (dev-environment, task, service, fleet, etc)
  dstack fleet --help                         # Fleet subcommands
  dstack ps --help                            # Flags for ps
  ```
- If a command or flag isn't documented, it doesn't exist.

### Command timing and confirmation handling

**Commands that stream indefinitely in the foreground:**
- `dstack attach`
- `dstack apply` without `-d` for runs
- `dstack ps -w`

Agents should avoid blocking: use `-d`, timeouts, or background attach. When attach is needed, run it in the background by default (`nohup ...`), but describe it to the user simply as "attach" unless they ask for a live foreground session. Prefer `dstack ps -v` and poll in a loop if the user wants to watch status.

**All other commands:** Use 10-60s timeout. Most complete within this range. **While waiting, monitor the output** - it may contain errors, warnings, or prompts requiring attention.

**Confirmation handling:**
- `dstack apply`, `dstack stop`, `dstack fleet delete` require confirmation
- Use `-y` flag to auto-confirm when user has already approved
- For `dstack stop`, always use `-y` after the user confirms to avoid interactive prompts
- Use `echo "n" |` to preview `dstack apply` plan without executing (avoid `echo "y" |`, prefer `-y`)

**Best practices:**
- Prefer modifying configuration files over passing parameters to `dstack apply` (unless it's an exception)
- When user confirms deletion/stop operations, use `-y` flag to skip confirmation prompts

### Detached run follow-up (after `-d`)

After submitting a run with `-d` (dev-environment, task, service), first determine whether submission failed. If the apply output shows errors (validation, no offers, etc.), stop and surface the error.

If the run was submitted, do a quick status check with `dstack ps -v`, then guide the user through relevant next steps:
If you need to prompt for next actions, be explicit about the dstack step and command (avoid vague questions). When speaking to the user, refer to the action as "attach" (not "background attach").
- **Monitor status:** Report the current status (provisioning/pulling/running/finished) and offer to keep watching. Poll `dstack ps -v` every 10-20s if the user wants updates.
- **Attach when running:** For agents, run attach in the background by default so the session does not block. Use it to capture IDE links/SSH alias or enable port forwarding; when describing the action to the user, just say "attach".
- **Dev environments or tasks with ports:** Once `running`, attach to surface the IDE link/port forwarding/SSH alias, then ask whether to open the IDE link. Never open links without explicit approval.
- **Services:** Prefer using service endpoints. Attach only if the user explicitly needs port forwarding or full log replay.
- **Tasks without ports:** Default to `dstack logs` for progress; attach only if full log replay is required.

### Attaching behavior (blocking vs non-blocking)

`dstack attach` runs until interrupted and blocks the terminal. **Agents must avoid indefinite blocking.** If a brief attach is needed, use a timeout to capture initial output (IDE link, SSH alias) and then detach.

Note: `dstack attach` writes SSH alias info under `~/.dstack/ssh/config` (and may update `~/.ssh/config`) to enable `ssh <run name>`, IDE connections, port forwarding, and real-time logs (`dstack attach --logs`). If the sandbox cannot write there, the alias will not be created.

**Permissions guardrail:** If `dstack attach` fails due to sandbox permissions, request permission escalation to run it outside the sandbox. If escalation isn’t approved or attach still fails, ask the user to run `dstack attach` locally and share the IDE link/SSH alias output.

**Background attach (non-blocking default for agents):**
```bash
nohup dstack attach <run name> --logs > /tmp/<run name>.attach.log 2>&1 & echo $! > /tmp/<run name>.attach.pid
```
Then read the output:
```bash
tail -n 50 /tmp/<run name>.attach.log
```
Offer live follow only if asked:
```bash
tail -f /tmp/<run name>.attach.log
```
Stop the background attach (preferred):
```bash
kill "$(cat /tmp/<run name>.attach.pid)"
```
If the PID file is missing, fall back to a specific match (avoid killing all attaches):
```bash
pkill -f "dstack attach <run name>"
```
**Why this helps:** it keeps the attach session alive (including port forwarding) while the agent remains usable. IDE links and SSH instructions appear in the log file -- surface them and ask whether to open the link (`open "<link>"` on macOS, `xdg-open "<link>"` on Linux) only after explicit approval.

If background attach fails in the sandbox (permissions writing `~/.dstack` or `~/.ssh`, timeouts), request escalation to run attach outside the sandbox. If not approved, ask the user to run attach locally and share the IDE link/SSH alias.

### Interpreting user requests

**"Run something":** When the user asks to run a workload (dev environment, task, service), use `dstack apply` with the appropriate configuration. Note: `dstack run` only supports `dstack run get --json` for retrieving run details -- it cannot start workloads.

**"Connect to" or "open" a dev environment:** If a dev environment is already running, use `dstack attach <run name> --logs` (agent runs it in the background by default) to surface the IDE URL (`cursor://`, `vscode://`, etc.) and SSH alias. If sandboxed attach fails, request escalation or ask the user to run attach locally and share the link.

## Configuration types

`dstack` supports five main configuration types. Configuration files can be named `<name>.dstack.yml` or simply `.dstack.yml`.

**Common parameters:** All run configurations (dev environments, tasks, services) support many parameters including:
- **Git integration:** Clone repos automatically (`repo`), mount existing repos (`repos`), upload local files (`working_dir`)
- **File upload:** `files` (see concept docs for examples)
- **Docker support:** Use custom Docker images (`image`); use `docker: true` if you want to use Docker from inside the container (VM-based backends only)
- **Environment:** Set environment variables (`env`), often via `.envrc`. Secrets are supported but less common.
- **Storage:** Persistent network volumes (`volumes`), specify disk size
- **Resources:** Define GPU, CPU, memory, and disk requirements

**Best practices:**
- Prefer giving configurations a `name` property for easier management
- When configurations need credentials (API keys, tokens), list only env var names in the `env` section (e.g., `- HF_TOKEN`), not values. Recommend storing actual values in a `.envrc` file alongside the configuration, applied via `source .envrc && dstack apply`.

### 1. Dev environments
**Use for:** Interactive development with IDE integration (VS Code, Cursor, etc.).

```yaml
type: dev-environment
name: cursor

python: "3.12"
ide: vscode

resources:
  gpu: 80GB
```

[Concept documentation](https://dstack.ai/docs/concepts/dev-environments.md) | [Configuration reference](https://dstack.ai/docs/reference/dstack.yml/dev-environment.md)

### 2. Tasks
**Use for:** Batch jobs, training runs, fine-tuning, web applications, any executable workload.

**Key features:** Distributed training (multi-node) and port forwarding for web apps.

```yaml
type: task
name: train

python: "3.12"
env:
  - HUGGING_FACE_HUB_TOKEN
commands:
  - uv pip install -r requirements.txt
  - uv run python train.py
ports:
  - 8501  # Optional: expose ports for web apps

resources:
  gpu: A100:40GB:2
```

**Port forwarding:** When you specify `ports`, `dstack apply` forwards them to `localhost` while attached. Use `dstack attach <run name>` to reconnect and restore port forwarding. The run name becomes an SSH alias (e.g., `ssh <run name>`) for direct access.

**Distributed training:** Multi-node tasks are supported (e.g., via `nodes`) and require fleets that support inter-node communication (see `placement: cluster` in fleets).

[Concept documentation](https://dstack.ai/docs/concepts/tasks.md) | [Configuration reference](https://dstack.ai/docs/reference/dstack.yml/task.md)

### 3. Services
**Use for:** Deploying models or web applications as production endpoints.

**Key features:** OpenAI-compatible model serving, auto-scaling (RPS/queue), custom gateways with HTTPS.

```yaml
type: service
name: llama31

python: "3.12"
env:
  - HF_TOKEN
commands:
  - uv pip install vllm
  - uv run vllm serve meta-llama/Meta-Llama-3.1-8B-Instruct
port: 8000
model: meta-llama/Meta-Llama-3.1-8B-Instruct

resources:
  gpu: 80GB
  disk: 200GB
```

**Service endpoints:**
- Without gateway: `<dstack server URL>/proxy/services/f/<run name>/`
- With gateway: `https://<run name>.<gateway domain>/`
- Authentication: Unless `auth` is `false`, include `Authorization: Bearer <DSTACK_TOKEN>` on all service requests.
- Model endpoint: If `model` is set, `service.model.base_url` from `dstack run get <run name> --json` provides the model endpoint. For OpenAI-compatible models (the default, unless format is set otherwise), this will be `service.url` + `/v1`.
- Example (with gateway):
  ```bash
  curl -sS -X POST "https://<run name>.<gateway domain>/v1/chat/completions" \
    -H "Authorization: Bearer <dstack token>" \
    -H "Content-Type: application/json" \
    -d '{"model":"<model name>","messages":[{"role":"user","content":"Hello"}],"max_tokens":64}'

[Concept documentation](https://dstack.ai/docs/concepts/services.md) | [Configuration reference](https://dstack.ai/docs/reference/dstack.yml/service.md)

### 4. Fleets
**Use for:** Pre-provisioning infrastructure for workloads, managing on-prem GPU servers, creating auto-scaling instance pools.

```yaml
type: fleet
name: my-fleet
nodes: 0..2

resources:
  gpu: 24GB..
  disk: 200GB

spot_policy: auto # other values: spot, on-demand
idle_duration: 5m
```

**On-demand provisioning:** When `nodes` is a range (e.g., `0..2`), dstack creates a template and provisions instances on demand within the min/max. Use `idle_duration` to terminate idle instances.

**Distributed workloads:** Use `placement: cluster` for fleets intended for multi-node tasks that require inter-node networking.

**SSH fleet (on-prem or pre-provisioned):**
```yaml
type: fleet
name: on-prem-fleet

ssh_config:
  user: ubuntu
  identity_file: ~/.ssh/id_rsa
  hosts:
    - 192.168.1.10
    - 192.168.1.11
```

[Concept documentation](https://dstack.ai/docs/concepts/fleets.md) | [Configuration reference](https://dstack.ai/docs/reference/dstack.yml/fleet.md)

### 5. Volumes
**Use for:** Persistent storage for datasets, model checkpoints, training artifacts.

```yaml
type: volume
name: my-volume

backend: aws
region: us-east-1

resources:
  disk: 500GB
```

**Instance volumes (local, ephemeral, often optional):**
```yaml
type: dev-environment
# ... other config
volumes:
  - instance_path: /dstack-cache/pip
    path: /root/.cache/pip
    optional: true
  - instance_path: /dstack-cache/huggingface
    path: /root/.cache/huggingface
    optional: true
```

**Attach to runs:** Use `volumes` in dev environments, tasks, and services. Network volumes persist independently; instance volumes are tied to the instance lifecycle.

[Concept documentation](https://dstack.ai/docs/concepts/volumes.md) | [Configuration reference](https://dstack.ai/docs/reference/dstack.yml/volume.md)

## Essential CLI commands

### Apply configurations

**Important behavior:**
- `dstack apply` shows a plan with estimated costs and may ask for confirmation
- In attached mode (default), the terminal blocks and shows output
- In detached mode (`-d`), runs in background without blocking the terminal

**Workflow for applying run configurations (dev-environment, task, service):**

1. **Show plan:**
   ```bash
   echo "n" | dstack apply -f config.dstack.yml
   ```
   Display the FULL output including the offers table and cost estimate. **Do NOT summarize or reformat.**

2. **Wait for user confirmation.** Do NOT proceed if:
   - Output shows "No offers found" or similar errors
   - Output shows validation errors
   - User has not explicitly confirmed

3. **Execute (only after user confirms):**
   ```bash
   dstack apply -f config.dstack.yml -y -d
   ```

4. **Verify apply status:**
   ```bash
   dstack ps -v
   ```

**Workflow for infrastructure (fleet, volume, gateway):**

1. **Show plan:**
   ```bash
   echo "n" | dstack apply -f fleet.dstack.yml
   ```
   Display the FULL output. **Do NOT summarize or reformat.**

2. **Wait for user confirmation.**

3. **Execute:**
   ```bash
   dstack apply -f fleet.dstack.yml -y
   ```

4. **Verify:** Use `dstack fleet`, `dstack volume`, or `dstack gateway` respectively.

### Fleet management

```bash
# Create/update fleet
dstack apply -f fleet.dstack.yml

# List fleets
dstack fleet

# Get fleet details
dstack fleet get my-fleet

# Get fleet details as JSON (for troubleshooting)
dstack fleet get my-fleet --json

# Delete entire fleet (use -y when user already confirmed)
dstack fleet delete my-fleet -y

# Delete specific instance from fleet (use -y when user already confirmed)
dstack fleet delete my-fleet -i <instance num> -y
```

### Monitor runs

```bash
# List all runs
dstack ps

# Verbose output with full details
dstack ps -v

# JSON output (for troubleshooting/scripting)
dstack ps --json

# Get specific run details as JSON
dstack run get my-run-name --json
```

### Attach to runs

```bash
# Attach and replay logs from start (preferred, unless asked otherwise)
dstack attach my-run-name --logs

# Attach without replaying logs (restores port forwarding + SSH only)
dstack attach my-run-name
```

### View logs

```bash
# Stream logs (tail mode)
dstack logs my-run-name

# Debug mode (includes additional runner logs)
dstack logs my-run-name -d

# Fetch logs from specific replica (multi-node runs)
dstack logs my-run-name --replica 1

# Fetch logs from specific job
dstack logs my-run-name --job 0
```

### Stop runs

```bash
# Stop specific run (use -y after user confirms)
dstack stop my-run-name -y

# Abort (force stop)
dstack stop my-run-name --abort
```

### List offers

Offers represent available instance configurations available for provisioning across backends. `dstack offer` lists offers regardless of configured fleets.

```bash
# Filter by specific backend
dstack offer --backend aws

# Filter by GPU type
dstack offer --gpu A100

# Filter by GPU memory
dstack offer --gpu 24GB..80GB

# Combine filters
dstack offer --backend aws --gpu A100:80GB

# JSON output (for troubleshooting/scripting)
dstack offer --json
```

**Max offers:** By default, `dstack offer` returns first N offers (output also includes the total number). Use `--max-offers N` to increase the limit.
**Grouping:** Prefer `--group-by gpu` (other supported values: `gpu,backend`, `gpu,backend,region`) for aggregated output across all offers, not `--max-offers`.

## Troubleshooting

When diagnosing issues with dstack workloads or infrastructure:

1. **Use JSON output for detailed inspection:**
   ```bash
   dstack fleet get my-fleet --json
   dstack run get my-run --json
   dstack ps -n 10 --json
   dstack offer --json
   ```

2. **Check verbose run status:**
   ```bash
   dstack ps -v
   ```

3. **Examine logs with debug output:**
   ```bash
   dstack logs my-run -d
   ```

4. **Attach with log replay:**
   ```bash
   dstack attach my-run --logs
   ```

Common issues:
- **No offers:** Check `dstack offer` and ensure that at least one fleet matches requirements
- **No fleet:** Ensure at least one fleet is created
- **Configuration errors:** Validate YAML syntax; check `dstack apply` output for specific errors
- **Provisioning timeouts:** Use `dstack ps -v` to see provisioning status; consider spot vs on-demand
- **Connection issues:** Verify server status, check authentication, ensure network access to backends

**When errors occur:**
1. Display the full error message unchanged
2. Do NOT retry the same command without addressing the error
3. Refer to the [Troubleshooting guide](https://dstack.ai/docs/guides/troubleshooting.md) for guidance

## Additional resources

**Core documentation:**
- [Overview](https://dstack.ai/docs/overview.md)
- [Installation](https://dstack.ai/docs/installation.md)
- [Quickstart](https://dstack.ai/docs/quickstart.md)

**Additional concepts:**
- [Secrets](https://dstack.ai/docs/concepts/secrets.md)
- [Projects](https://dstack.ai/docs/concepts/projects.md)
- [Metrics](https://dstack.ai/docs/concepts/metrics.md)
- [Events](https://dstack.ai/docs/concepts/events.md)

**Guides:**
- [Server deployment](https://dstack.ai/docs/guides/server-deployment.md)
- [Pro tips](https://dstack.ai/docs/guides/protips.md)

**Accelerator-specific examples:**
- [AMD](https://dstack.ai/examples/accelerators/amd/index.md)
- [Google TPU](https://dstack.ai/examples/accelerators/tpu/index.md)
- [Tenstorrent](https://dstack.ai/examples/accelerators/tenstorrent/index.md)

**Full documentation:** https://dstack.ai/llms-full.txt
