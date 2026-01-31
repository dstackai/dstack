---
name: dstack
description: |
  dstack is an open-source control plane for GPU provisioning and orchestration across GPU clouds, Kubernetes, and on-prem clusters.
---

# dstack

## Overview

`dstack` is a unified control plane that provisions and orchestrates GPU workloads across [GPU clouds and Kubernetes clusters](https://dstack.ai/docs/concepts/backends.md) or on-prem clusters (SSH fleets).

**When to use this skill:**
- Running GPU workloads (development, training, batch jobs, inference) across GPU clouds or on-prem GPU clusters
- Managing fleets of GPU instances (cloud or on-prem)
- Creating, editing, and running dstack configurations
- Troubleshooting GPU infrastructure and running workloads

## How it works

dstack operates through three core components:

1. `dstack` server - Control plane running locally, self-hosted, or via dstack Sky (managed)
2. `dstack` CLI - Command-line tool for applying configurations and managing workloads
3. `dstack` configuration files - YAML files  ending with `.dstack.yml`

**Typical workflow:**
```bash
# 1. Define configuration in YAML file (e.g., train.dstack.yml, .dstack.yml, llama-serve.dstack.yml)
# 2. Apply configuration
dstack apply -f train.dstack.yml

# 3. dstack provisions infrastructure and runs workload
# 4. Monitor with dstack ps, attach with dstack attach
```

The CLI applies configurations via `dstack apply`, which provisions infrastructure, schedules workloads, and manages lifecycle. Runs can be "attached" mode (by default) - interactive, blocks terminal with port forwarding and SSH access, or detached (via `-d`) – background, non-interactive.

**CRITICAL: Never propose dstack commands or command syntaxes that don't exist.**
- Only use commands and syntaxes explicitly documented in this skill file or verified via `--help`
- If uncertain about a command or its syntax, check the documentation or use `--help` rather than guessing
- Do not invent or assume command names, flags, or argument patterns
 
**Best practices:**
- Prefer giving run configurations a `name` property for easier management and identification
- Prefer modifying configuration files over passing parameters to `dstack apply` (unless it's an exception)
- When user confirms deletion/stop operations, use `-y` flag to skip confirmation prompts
- Many dstack commands require confirmation - pay attention to command output and respond appropriately rather than waiting indefinitely

## Configuration types

`dstack` supports five main configuration types, each with specific use cases. Configuration files can be named `<name>.dstack.yml` or simply `.dstack.yml`.

**Common parameters:** All run configurations (dev environments, tasks, services) support many parameters including:
- **Git integration:** Clone repos automatically (`repo`), mount existing repos (`repos`), upload local files (`working_dir`)
- **Docker support:** Use custom Docker images (`image`), enable Docker CLI inside workloads with `docker: true` (VM-based backends only)
- **Environment & secrets:** Set environment variables (`env`), reference secrets
- **Storage:** Mount persistent volumes (`volumes`), specify disk size
- **Resources:** Define GPU, CPU, memory, and disk requirements

See configuration reference pages for complete parameter lists.

### 1. Dev environments
**Use for:** Interactive development with IDE integration (VS Code, Cursor, etc.).

```yaml
type: dev-environment
python: "3.11"
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
python: "3.11"
env:
  - HUGGING_FACE_HUB_TOKEN
commands:
  - pip install -r requirements.txt
  - python train.py
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
python: "3.11"
env:
  - HF_TOKEN
commands:
  - pip install vllm
  - vllm serve meta-llama/Meta-Llama-3.1-8B-Instruct
port: 8000
model: meta-llama/Meta-Llama-3.1-8B-Instruct

resources:
  gpu: 80GB
  disk: 200GB

scaling:
  metric: rps
  target: 10
```

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
  disk: 100GB

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

**Requirements:** Hosts must have Docker, GPU drivers, passwordless sudo, and SSH port forwarding enabled.

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

## Essential Commands

### Apply Configurations

**Important behavior:**
- `dstack apply` shows a plan with estimated costs and may ask for confirmation (respond with `y` or use `-y` flag to skip)
- Once confirmed, it provisions infrastructure and streams real-time output to the terminal
- In attached mode (default), the terminal blocks and shows output - use timeout or Ctrl+C to interrupt if you need to continue with other commands
- In detached mode (`-d`), runs in background without blocking the terminal

**Workflow for applying configurations:**

**Important: When displaying CLI output, keep it close to the original format. Prefer showing tables as-is rather than reformatting or summarizing.**

**For run configurations (dev-environment, task, service):**
1. Show the plan by running `echo "n" | dstack apply -f <dstack config file>` and display output as-is
2. Ask user for confirmation
3. Once confirmed, run `dstack apply -f <dstack config file> -y -d` (detached mode with auto-confirm)
4. Show run status with `dstack ps`

**For other configurations (fleet, volume, gateway):**
1. Show the plan by running `dstack apply -f <dstack config file>` (these don't support the "n" trick or `-d` flag)
2. Ask user for confirmation
3. Once confirmed, run `dstack apply -f <dstack config file> -y`
4. Show status with the appropriate command:
   - Fleets: `dstack fleet`
   - Volumes: `dstack volume`
   - Gateways: `dstack gateway`

```bash
# Apply and attach (interactive, blocks terminal with port forwarding)
dstack apply -f train.dstack.yml

# Apply with automatic confirmation
dstack apply -f train.dstack.yml -y

# Apply detached (background, no attachment)
dstack apply -f serve.dstack.yml -d

# Force rerun
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

# Delete specific instance from fleet (use -y when user already confirmed)
dstack fleet delete-instance my-fleet <instance-id> -y
```

### Monitor Runs

```bash
# List all runs
dstack ps

# JSON output (for troubleshooting/scripting)
dstack ps --json

# Verbose output with full details
dstack ps -v

# Watch mode (auto-refresh)
dstack ps -w

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

### View Logs

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

**Note:** `dstack offer` shows all available GPU instances from configured backends, not just those in fleets. Use it to discover what resources are available for provisioning.

```bash
# List available GPU offers from all backends
dstack offer

# Filter by backend
dstack offer --backend aws

# Filter by GPU requirements
dstack offer --gpu A100
```

## Troubleshooting

When diagnosing issues with dstack workloads or infrastructure:

1. **Use JSON output for detailed inspection:**
   ```bash
   dstack fleet get my-fleet --json | jq .
   dstack run get my-run --json | jq .
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

5. **Check fleet capacity:**
   ```bash
   dstack fleet get my-fleet  # View current instances and utilization
   ```

6. **Verify resource availability:**
   ```bash
   dstack offer --backend aws --gpu A100  # Check if resources exist
   ```

Common issues:
- **No capacity errors:** Check `dstack offer` for availability, adjust resource requirements, or enable more backends
- **No matching fleet:** Ensure at least one fleet matches workload resource requirements; use `dstack fleet` to list configured fleets
- **Configuration errors:** Validate YAML syntax; check `dstack apply` output for specific errors
- **Provisioning timeouts:** Use `dstack ps -v` to see provisioning status; consider spot vs on-demand
- **Connection issues:** Verify server status, check authentication, ensure network access to backends
- **Resource mismatch:** Check that fleet resource specs (GPU type, memory, disk) are compatible with workload requirements

[Troubleshooting guide](https://dstack.ai/docs/guides/troubleshooting.md)

## Additional Resources

**Core Documentation:**
- [Overview](https://dstack.ai/docs/overview.md)
- [Installation](https://dstack.ai/docs/installation.md)
- [Quickstart](https://dstack.ai/docs/quickstart.md)

**Additional Concepts:**
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

**Full Documentation:** https://dstack.ai/llms-full.txt
