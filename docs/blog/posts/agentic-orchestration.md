---
title: "Infrastructure orchestration is an agent skill"
date: 2026-03-10
description: "Agentic engineering pulls compute discovery, provisioning, scheduling, and observability into the execution loop. Infrastructure orchestration is becoming an agent skill."
slug: agentic-orchestration
image: https://dstack.ai/static-assets/static-assets/images/agentic-orchestration.png
categories:
  - Changelog
---

# Infrastructure orchestration is an agent skill

Andrej Karpathy's [autoresearch demo](https://github.com/karpathy/autoresearch) shows the main change: the agent does not stop at suggesting code. It runs experiments, evaluates the results, commits improvements, and repeats the cycle. Execution itself is now inside the loop.

<img src="https://dstack.ai/static-assets/static-assets/images/agentic-orchestration.png" width="630" />

<!-- more -->

Once execution is inside the loop, infrastructure is no longer just setup around it. The agent also needs to provision compute, run workloads, inspect what happened, and decide what to do next.

This post is about that emerging shift: infrastructure orchestration becoming part of the agent loop.

## Before: orchestration assumed a human control loop

Until now, orchestration for AI workloads has usually been owned by platform teams.

Those teams automated provisioning, prepared runtime environments, scheduled workloads, and operated the infrastructure. Automation existed, but the orchestration loop itself still required human intervention.

That model fits a world where infrastructure operations stay separate from the training, evaluation, and inference workflow itself. The emerging agentic workflow pulls orchestration into the loop.

## After: provisioning and scheduling move into the loop

If an agent is driving a training, evaluation, or inference workflow, it cannot stop at generating code or launching a job. It also has to provision the right compute, place workloads efficiently, observe execution state, and adjust based on the result.

That is the shift: compute provisioning and scheduling move into the agent loop. If platform teams are no longer in the hot path for each step, orchestration has to expose explicit primitives for capacity discovery, bounded provisioning, workload lifecycle management, and machine-readable state.

Without those primitives, the workflow still depends on manual intervention or a bespoke internal platform layer.

## What this does to platform teams

Platform teams are not going to stay in the business of manually orchestrating AI infrastructure. The old model treats orchestration as an internal service layer that humans operate on behalf of everyone else. In the emerging model, that ownership shifts.

The platform team's job becomes enabling agent-driven orchestration and controlling it safely. That means defining the supported abstractions, access boundaries, budgets, quotas, and observability that let agents provision compute and operate workloads directly without turning the platform into an unbounded automation surface.

## What this does to cloud and datacenter providers

For cloud and datacenter providers, orchestration stops being a detail above the hardware stack and becomes part of the product. Their capacity is no longer consumed only by humans or by platform teams operating custom glue. It is increasingly consumed through the orchestration layer that sits between the workload and the provider.

That changes what makes capacity usable. A provider now has to fit the vendor-agnostic orchestration layer that agents use to discover capacity, provision it, schedule workloads, and observe state. 

Providers that fit that layer become much easier to integrate into agent-driven systems. Providers that still require provider-specific operating patterns remain harder to operationalize, even when the underlying hardware is strong.

## What this looks like with dstack

dstack is an open-source control plane for provisioning GPU compute and orchestrating GPU workloads across a range of environments, including clouds, Kubernetes, and on-prem clusters. It exposes that infrastructure surface to agents and human operators through the CLI and configuration files.

**Step 1: treat available compute as queryable state**

`dstack offer` turns available compute into something the workflow can query directly. It returns offers from configured backends and managed capacity, including region, resources, spot availability, and price.

```shell
dstack offer --gpu H100:1.. --max-offers 3
```

```shell
#   BACKEND  REGION     INSTANCE TYPE          RESOURCES                                     SPOT  PRICE
1   verda    FIN-01     1H100.80S.30V          30xCPU, 120GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.19
2   runpod   US-KS-2    NVIDIA H100 PCIe       16xCPU, 251GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.39
3   nebius   eu-north1  gpu-h100-sxm           16xCPU, 200GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.95
    ...
Shown 3 of 99 offers
```

In an agentic workflow, compute selection becomes part of execution. The workflow can inspect available capacity before deciding what to run.

**Step 2: define capacity pools and provisioning bounds**

```yaml
# fleet.dstack.yml
type: fleet
name: h100-fleet

nodes: 0..2
idle_duration: 1h

resources:
  gpu: H100:8

blocks: 4
```

A fleet is dstack's unit of provisioning control. It can represent an elastic template over cloud or Kubernetes backends, a pre-provisioned pool, or a set of SSH-managed on-prem hosts. This is how dstack keeps provisioning explicit and bounded: the agent operates within declared capacity instead of interacting with provider infrastructure directly.

```shell
dstack apply -f fleet.dstack.yml
```

In this context, `dstack apply` creates or updates the fleet resource. If the fleet is only a template, later runs can draw instances from it on demand. If it is pre-provisioned, the capacity is already present.

```shell
dstack fleet

 NAME         NODES  GPU           SPOT       BACKEND       PRICE    STATUS  CREATED
 gpu-cluster  2..4   A100:80GB:8   auto       aws           $0..$32  active  2 hours ago
   instance=0        A100:80GB:8   spot       aws (us-ea…)  $28.50   busy    2 hours ago
   instance=1        A100:80GB:8   spot       gcp (us-ce…)  $26.80   busy    1 hour ago
 on-prem      4      -             -          ssh           -        active  3 days ago
   instance=0        A100:40GB:4   -          ssh           -        busy    3 days ago
   instance=1        A100:40GB:4   -          ssh           -        idle    3 days ago
 test-fleet   0..1   gpu:16GB      on-demand  *             -        active  10 min ago
```

In an agentic workflow, this gives the agent a visible provisioning surface: it can see which fleets exist, what capacity they expose, and whether that capacity is active, busy, or idle before deciding what to run next.

**Step 3: run evaluation or training loops as tasks**

Tasks are dstack's workload type for evaluation, fine-tuning, training, and other job-oriented workflows. They can also be distributed, in which case dstack handles cluster selection and job coordination across nodes.

```yaml
# train.dstack.yml
type: task
name: train-qwen

image: huggingface/trl-latest-gpu
working_dir: /workspace

repos:
  - .:/workspace

commands:
  - pip install -r requirements.txt
  - python train.py --model Qwen/Qwen2.5-7B-Instruct --output-dir /workspace/checkpoints

max_duration: 2h
resources:
  gpu: 24GB
  shm_size: 16GB
```

Once a task is running, the agent may need to re-attach to the session, open a shell inside the container, or inspect runtime state before deciding what to do next. dstack exposes each of those actions directly.

```shell
dstack attach train-qwen --logs
```

```shell
ssh train-qwen
```

**Step 4: run model inference as services**

Services are dstack's workload type for long-lived inference endpoints. The same control plane that runs training and evaluation jobs can also deploy model-serving endpoints with stable URLs, autoscaling rules, and health checks.

```yaml
# serve.dstack.yml
type: service
name: qwen25-instruct

image: lmsysorg/sglang:latest

env:
  - MODEL_ID=Qwen/Qwen2.5-32B-Instruct

commands:
  - |
    python -m sglang.launch_server \
      --model-path $MODEL_ID \
      --port 8000 \
      --trust-remote-code

port: 8000
gateway: true
model: Qwen/Qwen2.5-32B-Instruct
replicas: 1..4
scaling:
  metric: rps
  target: 10

resources:
  gpu: 80GB
  disk: 200GB
```

The endpoint can then be accessed directly, including from another agent step:

```shell
curl https://qwen25-instruct.example.com/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <dstack token>' \
  -d '{
    "model": "Qwen/Qwen2.5-32B-Instruct",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

The agent can launch the service, call the endpoint, and scale it through the same orchestration layer.

**Step 5: observe through events and metrics**

`dstack` exposes structured lifecycle data through events and metrics, so the loop can inspect state transitions and resource usage directly instead of inferring everything from logs.

```shell
dstack event --within-run train-qwen
```

```shell
[2026-01-21 13:09:37] [run train-qwen] Run submitted. Status: SUBMITTED
[2026-01-21 13:09:57] [job train-qwen-0-0] Job status changed SUBMITTED -> PROVISIONING
[2026-01-21 13:11:49] [job train-qwen-0-0] Job status changed PULLING -> RUNNING
```

```shell
dstack metrics train-qwen
```

```shell
 NAME        STATUS   CPU  MEMORY       GPU
 train-qwen  running  92%  118GB/200GB  gpu=0 mem=71GB/80GB util=97%
```

Taken together, these are the fine-grained primitives a fully autonomous agent needs: discover capacity, provision it, run the right workload type, inspect state, and decide what to do next without handing orchestration back to a human operator.

## Skills

Those primitives become much more useful when they are paired with operational knowledge. dstack already ships an installable [agent skill](https://github.com/dstackai/dstack/blob/master/.agents/skills/dstack/SKILL.md) and documents how to install it:

```shell
npx skills add dstackai/dstack
```

> Skills are where operational know-how can live: how to run training, fine-tuning, inference, evals, and other specialized workflows against the orchestration layer. This should not stop at one built-in skill. The ecosystem needs specialized skills that encode the operational patterns agents actually use for these workloads.

## Governance and permissions

As infrastructure management is delegated to agents, governance and observability become part of the orchestration model itself, not something added later around it.

dstack already exposes part of that model through projects and permissions. Projects isolate teams and resources, define access boundaries, and control which backends and infrastructure surfaces an agent or user can operate against.

## Why open source and the ecosystem matter here

If agents are going to provision compute and orchestrate workloads directly, the control plane cannot be a black box.

Teams need to see which backends it supports, how scheduling decisions are made, how permissions are enforced, and how lifecycle state is exposed. They also need to extend it: add new providers, refine operational policies, and encode better training, fine-tuning, inference, and evaluation workflows as reusable skills and recipes.

dstack is MPL-2.0 licensed and designed around backends, fleets, projects, events, and metrics that can span different capacity sources. That matters because agentic orchestration will not be built once inside a single vendor boundary; it will be assembled across clouds, Kubernetes, on-prem infrastructure, and a growing ecosystem of specialized operational patterns.

## What's next

If you are already running agent-driven loops, feedback on the hard parts is especially useful: what still forces a human back into the path, which signals are missing, where provider integration still feels manual, and which specialized skills or recipes would be most valuable.

If you want to use dstack for these workflows or contribute to the surrounding ecosystem, issues and feedback are welcome in the [GitHub repo](https://github.com/dstackai/dstack).
