---
name: dstack
description: |
  dstack is an open-source control plane for GPU provisioning and orchestration across GPU clouds, Kubernetes, and on-prem clusters.
---

# dstack

## Overview

`dstack` is a tool that allows to provision and orchestrate GPU workloads across [GPU clouds and Kubernetes clusters](https://dstack.ai/docs/concepts/backends.md) or on-prem clusters (SSH fleets).

**When to use this skill:**
- Running/managing GPU workloads (dev environments, tasks for training or other batch jobs, services to run inference or deploy web apps)
- Creating, editing, and running `dstack` configurations
- Managing fleets of compute (instances/clusters)

## How it works

`dstack` operates through three core components:

1. `dstack` server - Can run locally, remotely, or via dstack Sky (managed)
2. `dstack` CLI - For applying configurations and managing resources; CLI can be pointed to the server and a particular default project (`~/.dstack/config.yml` or via `dstack project` CLI command); other CLI commands use the default project
3. `dstack` configuration files - YAML files ending with `.dstack.yml`

**Typical workflow:**
```bash
# 1. Define configuration in YAML file (e.g., train.dstack.yml, .dstack.yml, llama-serve.dstack.yml)
# 2. Apply configuration
dstack apply -f train.dstack.yml

# 3. dstack prepares a plan, and once confirmed, provisions instances (according to created fleets) and runs workloads
# 4. Monitor with `dstack ps`, `dstack logs`, `dstack attach`, etc. (these commands support various options).
```

By default, `dstack apply` requires a confirmation, and once first job within the run is `running` - it "attaches" establishes an SSH tunnel, forwards ports if any and streams logs in real-time; if you pass `-d`, it runs in the detached mode and exits once the run is submitted.

**CRITICAL: Never propose `dstack` CLI commands or YAML syntaxes that don't exist.**
- Only use CLI commands and YAML syntax explicitly documented in this skill file or verified via `--help`
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

**This section provides critical guidance for AI agents executing dstack commands.**

### Output accuracy
- **NEVER reformat, summarize, or paraphrase CLI output.** Display tables, status output, and error messages exactly as returned.
- When showing command results, use code blocks to preserve formatting.
- If output is truncated due to length, indicate this clearly (e.g., "Output truncated. Full output shows X entries.").

### Verification before execution
- **When uncertain about any CLI flag or YAML property, run `dstack <command> --help` first.**
- Never guess or invent flags. Example verification commands:
  ```bash
  dstack --help                               # List all commands
  dstack apply --help <configuration tpye>    # Flags for apply per configuration type (dev-environment, task, service, fleet, etc)
  dstack fleet --help                         # Fleet subcommands
  dstack ps --help                            # Flags for ps
  ```
- If a command or flag isn't documented, it doesn't exist.

### Command timing and confirmation handling

**Commands that run indefinitely (agents should avoid these):**
- `dstack attach` - maintains connection until interrupted
- `dstack apply` without `-d` for runs - streams logs after provisioning
- `dstack ps -w` - watch mode, auto-refreshes until interrupted

Instead, use `dstack ps -v` to check status, or `dstack apply -d` for detached mode.

**All other commands:** Use 10-60s timeout. Most complete within this range. **While waiting, monitor the output** - it may contain errors, warnings, or prompts requiring attention.

**Confirmation handling:**
- `dstack apply`, `dstack stop`, `dstack fleet delete` require confirmation
- Use `-y` flag to auto-confirm when user has already approved
- Use `echo "n" |` to preview `dstack apply` plan without executing (avoid `echo "y" |`, prefer `-y`)

**Best practices:**
- Prefer modifying configuration files over passing parameters to `dstack apply` (unless it's an exception)
- When user confirms deletion/stop operations, use `-y` flag to skip confirmation prompts
- Avoid waiting indefinitely; display essential output once command is finished (even if by timeout)

## Configuration types

`dstack` supports five main configuration types, each with specific use cases. Configuration files can be named `<name>.dstack.yml` or simply `.dstack.yml`.

**Common parameters:** All run configurations (dev environments, tasks, services) support many parameters including:
- **Git integration:** Clone repos automatically (`repo`), mount existing repos (`repos`), upload local files (`working_dir`)
- **Docker support:** Use custom Docker images (`image`); Also if needed, use `docker: true` if you want to use `docker` from inside the container (VM-based backends only)
- **Environment & secrets:** Set environment variables (`env`), reference secrets
- **Storage:** Persistent network volumes (`volumes`), specify disk size
- **Resources:** Define GPU, CPU, memory, and disk requirements

**Best practices:**
 - Prefer giving configurations a `name` property for easier management

See configuration reference pages for complete parameter lists.

### 1. Dev environments
**Use for:** Interactive development with IDE integration (VS Code, Cursor, etc.).

```yaml
type: dev-environment
name: cursor

python: "3.12"
ide: vscode

resources:
  gpu: 80GB
  disk: 500GB
```

[Concept documentation](https://dstack.ai/docs/concepts/dev-environments.md) | [Configuration reference](https://dstack.ai/docs/reference/dstack.yml/dev-environment.md)

### 2. Tasks
**Use for:** Batch jobs, training runs, fine-tuning, web applications, any executable workload.

**Key features:** Distributed training (multi-node), port forwarding for web apps.

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
  gpu: A100:40GB:2  # Two 40GB A100s
  disk: 200GB
```

**Port forwarding:** When you specify `ports`, `dstack apply` automatically forwards them to `localhost` while attached. Use `dstack attach <run-name>` to reconnect and restore port forwarding. The run name becomes an SSH alias (e.g., `ssh <run-name>`) for direct access.

**Examples:**
- [Single-node training (TRL)](https://dstack.ai/examples/single-node-training/trl/index.md)
- [Single-node training (Axolotl)](https://dstack.ai/examples/single-node-training/axolotl/index.md)
- [Distributed training (TRL)](https://dstack.ai/examples/distributed-training/trl/index.md)
- [Distributed training (Axolotl)](https://dstack.ai/examples/distributed-training/axolotl/index.md)
- [Distributed training (Ray+RAGEN)](https://dstack.ai/examples/distributed-training/ray-ragen/index.md)
- [NCCL/RCCL tests](https://dstack.ai/examples/clusters/nccl-rccl-tests/index.md)

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

Once a service is `running` and its health probes are green:

**Service endpoints:**
- Without gateway: `<dstack server URL>/proxy/services/<project name>/<run name>/`
- With gateway: `https://<run name>.<gateway domain>/`

**Example:**
```bash
curl http://localhost:3000/proxy/services/<project name>/<run name>/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <dstack token>' \
  -d '{"model": "meta-llama/Meta-Llama-3.1-8B-Instruct", "messages": [{"role": "user", "content": "Hello!"}]}'
```

**Gateways:** Set up a [gateway](https://dstack.ai/docs/concepts/gateways.md) before running services to enable custom domains, HTTPS, auto-scaling rate limits, and production-grade endpoint management. Use the `dstack gateway` CLI command to manage gateways.

**Examples:**
- [SGLang](https://dstack.ai/examples/inference/sglang/index.md)
- [vLLM](https://dstack.ai/examples/inference/vllm/index.md)
- [NIM](https://dstack.ai/examples/inference/nim/index.md)
- [TensorRT-LLM](https://dstack.ai/examples/inference/trtllm/index.md)

[Concept documentation](https://dstack.ai/docs/concepts/services.md) | [Configuration reference](https://dstack.ai/docs/reference/dstack.yml/service.md)

### 4. Fleets
**Use for:** Pre-provisioning infrastructure for workloads, managing on-premises GPU servers, creating auto-scaling instance pools.

**Important:** Workloads (dev environments, tasks, services) only run if their resource requirements match at least one configured fleet. Without matching fleets, provisioning will fail.

dstack supports two fleet types:

#### Backend fleets (Cloud/Kubernetes)
Dynamically provision instances from configured [backends](https://dstack.ai/docs/concepts/backends.md). Use the `nodes` property for on-demand scaling:

```yaml
type: fleet
name: my-fleet
nodes: 0..2  # Range: creates template when starting with 0, provisions on-demand

resources:
  gpu: 24GB..  # 24GB or more
  disk: 200GB

spot_policy: auto  # auto (default), spot, or on-demand
idle_duration: 5m  # Terminate idle instances after 5 minutes
```

**On-demand provisioning:** When `nodes` is a range (e.g., `0..2`, `1..10`), dstack creates an instance template. Instances are provisioned automatically when workloads need them, scaling between min and max. Set `idle_duration` to terminate idle instances.

**Additional options:** Fleets support many configuration options including `placement: cluster` for multi-node distributed workloads requiring inter-node communication (e.g., multi-GPU training), `blocks` for resource isolation, environment variables, and more. See the configuration reference for complete details.

#### SSH fleets (on-prem or pre-provisioned clusters)
Use existing GPU servers accessible via SSH:

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
**Use for:** Persistent storage for datasets, model checkpoints, training artifacts that persist across runs and can be shared between workloads.

dstack supports two types of volumes:

#### Network Volumes
Backend-specific persistent volumes (AWS EBS, GCP Persistent Disk, etc.) that can be attached to any dev environment, task, or service.

**Define a network volume:**
```yaml
type: volume
name: my-volume

backend: aws
region: us-east-1

resources:
  disk: 500GB
```

**Attach to workloads via `volumes` property:**
```yaml
type: task
# ... other config
volumes:
  - name: my-volume
    path: /volume_data
```

#### Instance Volumes
Faster local volumes using the instance's root disk. Ideal for ephemeral storage, caching, or maximum I/O performance without persistence across instances.

**Attach instance volumes via `volumes` property:**
```yaml
type: dev-environment
# ... other config
volumes:
  - name: my-instance-volume
    path: /cache_data
```

**Note:** Volumes can be attached to dev environments, tasks, and services using the `volumes` property. Network volumes persist independently, while instance volumes are tied to the instance lifecycle.

[Concept documentation](https://dstack.ai/docs/concepts/volumes.md) | [Configuration reference](https://dstack.ai/docs/reference/dstack.yml/volume.md)

## Essential CLI commands

### Apply configurations

**Important behavior:**
- `dstack apply` shows a plan with estimated costs and may ask for confirmation (respond with `y` or use `-y` flag to skip)
- Once confirmed, it provisions infrastructure and streams real-time output to the terminal
- In attached mode (default), the terminal blocks and shows output - use timeout or Ctrl+C to interrupt if you need to continue with other commands
- In detached mode (`-d`), runs in background without blocking the terminal

**Workflow for applying configurations:**

> **Critical for agents:** Always show the plan first, wait for user confirmation, THEN execute. Never auto-execute without user approval.

**Step-by-step for run configurations (dev-environment, task, service):**

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
   Show the run status. Look for the run name and status column.

**Step-by-step for infrastructure (fleet, volume, gateway):**

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

**Common apply patterns:**
```bash
# Apply and attach (interactive, blocks terminal with port forwarding)
dstack apply -f train.dstack.yml

# Apply with automatic confirmation
dstack apply -f train.dstack.yml -y

# Apply detached (background, no attachment)
dstack apply -f serve.dstack.yml -d

# Force rerun (recreates even if run with same name exists)
dstack apply -f finetune.dstack.yml --force

# Override defaults (prefer modifying config file instead, unless it's an exception)
dstack apply -f .dstack.yml --max-price 2.5
```

### Fleet Management

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

# IMPORTANT: When asked to delete an instance, always use -i <instance num> - do NOT delete the entire fleet (use -y when user already confirmed)
dstack fleet delete my-fleet -i <instance num> -y
```

### Monitor runs

```bash
# List all runs
dstack ps

# JSON output (for troubleshooting/scripting)
dstack ps --json

# Verbose output with full details
dstack ps -v

# Get specific run details as JSON
dstack run get my-run-name --json
```

### Attach to runs

**What is attaching?** Attaching connects to an existing run to restore port forwarding (for tasks/services with ports) and enable SSH access. The run name becomes an SSH alias (e.g., `ssh my-run-name`) configured in `~/.dstack/ssh/config` (included to `~/.ssh/config`).

**Note:** `dstack apply` automatically attaches when run completes provisioning. Use `dstack attach` to reconnect after detaching or to access detached runs.

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
# Stop specific run
dstack stop my-run-name

# Stop with confirmation skipped (use when user already confirmed)
dstack stop my-run-name -y

# Abort (force stop)
dstack stop my-run-name --abort
```

### Check available resources

**Use `dstack offer` to verify GPU availability before provisioning:**

```bash
# List all available offers across backends
dstack offer --json

# Filter by specific backend
dstack offer --backend aws

# Filter by GPU type
dstack offer --gpu A100

# Filter by GPU memory
dstack offer --gpu 24GB..80GB

# JSON output for detailed inspection
dstack offer --json

# Combine filters
dstack offer --backend aws --gpu A100:80GB
```

**Note:** `dstack offer` shows all available GPU instances from configured backends, not just those matching configured fleets. Use it to check backend availability, but remember: an offer appearing here doesn't guarantee a fleet will provision it - fleets have their own resource constraints.

### Expected Output Formats

**Agents should display these tables as-is, preserving column alignment.**

## Troubleshooting

When diagnosing issues with dstack workloads or infrastructure:

1. **Use JSON output for detailed inspection:**
   ```bash
   dstack fleet get my-fleet --json | jq .
   dstack run get my-run --json | jq .
   dstack ps -n 10 --json | jq .
   ```

2. **Check verbose run status:**
   ```bash
   dstack ps -v  # Shows provisioning state, instance details, errors
   ```

3. **Examine logs with debug output:**
   ```bash
   dstack logs my-run -d  # Includes additional runner logs
   ```

4. **Attach with log replay:**
   ```bash
   dstack attach my-run --logs  # See full output from start
   ```

5. **Verify resource availability:**
   ```bash
   dstack offer --backend aws --gpu A100 --spot-auto --json  # Check if resources exist
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

## Additional Resources

**Core documentation:**
- [Overview](https://dstack.ai/docs/overview.md)
- [Installation](https://dstack.ai/docs/installation.md)
- [Quickstart](https://dstack.ai/docs/quickstart.md)

**Additional concepts:**
- [Secrets](https://dstack.ai/docs/concepts/secrets.md) - Manage sensitive credentials
- [Projects](https://dstack.ai/docs/concepts/projects.md) - Projects isolate the resources of different teams
- [Metrics](https://dstack.ai/docs/concepts/metrics.md) - Track GPU utilization
- [Events](https://dstack.ai/docs/concepts/events.md) - Monitor system events

**Guides:**
- [Server deployment](https://dstack.ai/docs/guides/server-deployment.md) (for server administration)
- [Pro tips](https://dstack.ai/docs/guides/protips.md)

**Accelerator-specific examples:**
- [AMD](https://dstack.ai/examples/accelerators/amd/index.md)
- [Google TPU](https://dstack.ai/examples/accelerators/tpu/index.md)
- [Tenstorrent](https://dstack.ai/examples/accelerators/tenstorrent/index.md)

**Full documentation:** https://dstack.ai/llms-full.txt
