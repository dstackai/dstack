---
title: "Infrastructure orchestration is an agent skill"
date: 2026-03-11
description: "Agentic engineering pulls compute discovery, provisioning, scheduling, and observability into the execution loop. Infrastructure orchestration is becoming an agent skill."
slug: agentic-orchestration
image: https://dstack.ai/static-assets/static-assets/images/agentic-orchestration.png
---

# Infrastructure orchestration is an agent skill

Andrej Karpathy’s [autoresearch](https://github.com/karpathy/autoresearch) demo is a crisp example of “agentic engineering” in practice: a short Markdown spec (`program.md`) drives an automated research cycle that iterates many times on one GPU with minimal human involvement. This post extends that same idea one layer down.

<img src="https://dstack.ai/static-assets/static-assets/images/agentic-orchestration.png" width="630" />

<!-- more -->

Closing a research loop on one GPU is already useful. Closing the full engineering loop—training jobs, evaluations, deploying inference endpoints, running regressions, rolling forward/back—forces one additional requirement: infrastructure orchestration has to be something an agent can do reliably.

## Before: orchestration lived outside the workload

Most orchestration approaches treat “what to run” and “where it runs” as separate.

Teams decide the placement context outside the workload: which cluster or region, which GPU class, which runtime image, which quota pool, which scheduling lane. The workload is then expressed in a way that assumes that context is already fixed.

That separation is not “wrong.” It matches how humans operate: decisions about capacity and placement are made deliberately, reviewed, and changed on a human timescale. The orchestrator executes inside a box that humans chose.

## After: provisioning and scheduling move into the loop

Agentic engineering collapses the separation.

When an agent is responsible for progress—not just for drafting code—compute choices affect how quickly it can iterate, what it can afford to try, and whether it can ship a result as a service. The orchestration decisions aren’t just “which cluster?”

Training often wants one shape of resources (long-running, stable, sometimes multi-GPU or multi-node). 

Evaluation wants another (many small runs, often interruptible). Inference wants another (a long-lived service with predictable restarts, health checks, and a stable endpoint). If those shapes require switching tools and rewriting glue each time, the “agent does execution” idea breaks down at the infrastructure boundary.

!!! info "Where orchestration becomes an agent skill"
    Orchestration becomes an agent skill when agents can choose and operate compute as part of execution, instead of handing infrastructure decisions back to a human.

## What “agent skill” means here

This isn’t about giving an agent raw cloud credentials and hoping for the best. “Agent skill” here means there is an interface and set of abstractions that are stable enough to teach, predictable enough to automate, and specific enough for GPU work.

An agent needs to reason about GPU constraints as first-class inputs: memory and count, placement for multi-node jobs, preemptible vs stable capacity, and the difference between “run 100 short evals” and “keep an inference endpoint alive.”

A true orchestration skill is one where the agent can answer, mechanically: what ran, where it ran, what resources it used, what state transitions happened, and what to do next.

## What this does to platform teams

The platform team shift is not “replace humans with agents.” It’s a change in what the platform optimizes for.

Platforms are often designed around human workflows: manual approvals, bespoke runbooks, and implicit institutional knowledge. Agentic engineering needs a different center of gravity: an agent-native control plane that exposes explicit building blocks for GPU jobs and inference services, plus the constraints that keep cost and risk bounded.

The old model treats orchestration as an internal service layer that humans operate on behalf of everyone else. In the emerging model, that ownership shifts.

The platform team's job becomes enabling agent-driven orchestration and controlling it safely. That means defining the supported abstractions, access boundaries, budgets, quotas, and observability that let agents provision compute and operate workloads directly without turning the platform into an unbounded automation surface.

## What this does to cloud and datacenter providers

For cloud and datacenter providers, GPUs don’t become less important; the interface around them becomes decisive for agent-operated workflows.

Agents need capacity to be discoverable, provisionable, and observable through repeatable semantics. A provider can have excellent hardware and still be painful to use if the operational contract is “humans click around and tribal-knowledge it into working.” In an agent-driven workflow, anything that can’t be expressed cleanly in an orchestration interface becomes friction.

That’s why multi-environment orchestration layers matter. They don’t only reduce vendor lock-in; they make capacity usable by automation, which is increasingly the consumer.

Providers that still require provider-specific operating patterns remain harder to operationalize, even when the underlying hardware is strong.

## What this looks like with dstack

`dstack` is an open-source control plane for GPU provisioning and orchestration across GPU clouds and on-prem clusters, with a workflow model that explicitly targets development, training, and inference.

The way to read `dstack` is as a CLI with a small set of abstractions that line up with the agent-skill requirements above.

**Step 1: treat available compute as queryable state**

`dstack` exposes “offers” as a way to query available hardware configurations from configured backends or on-prem clusters. That turns “where can I run this?” into something automation can ask and answer deterministically, instead of hard-coding instance types and regions.

```shell
$ dstack offer --gpu H100:1.. --max-offers 3

 #   BACKEND  REGION     INSTANCE TYPE          RESOURCES                                     SPOT  PRICE
 1   verda    FIN-01     1H100.80S.30V          30xCPU, 120GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.19
 2   runpod   US-KS-2    NVIDIA H100 PCIe       16xCPU, 251GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.39
 3   nebius   eu-north1  gpu-h100-sxm           16xCPU, 200GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.95
     ...
 Shown 3 of 99 offers
```

**Step 2: define capacity pools and provisioning bounds**

Fleets are `dstack`’s way to make capacity explicit. A fleet can represent elastic capacity (scale from zero on demand) or a pre-provisioned pool (including SSH-managed on-prem hosts). It also supports operational patterns that matter for GPU efficiency, such as splitting a multi-GPU node into blocks so that many small jobs don’t waste a full 8-GPU box. The agent operates within declared capacity instead of interacting with provider infrastructure directly.

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

<div class="termy">

```shell
$ dstack apply -f fleet.dstack.yml
```

</div>

If the fleet is elastic (`nodes` set to a range), later runs can provision instances on demand. If it is pre-provisioned, the capacity is already present.

<div class="termy">

```shell
$ dstack fleet

 NAME         NODES  GPU           SPOT       BACKEND       PRICE    STATUS  CREATED
 gpu-cluster  2..4   A100:80GB:8   auto       aws           $0..$32  active  2 hours ago
   instance=0        A100:80GB:8   spot       aws (us-ea…)  $28.50   busy    2 hours ago
   instance=1        A100:80GB:8   spot       gcp (us-ce…)  $26.80   busy    1 hour ago
 on-prem      2      -             -          ssh           -        active  3 days ago
   instance=0        A100:40GB:4   -          ssh           -        busy    3 days ago
   instance=1        A100:40GB:4   -          ssh           -        idle    3 days ago
 test-fleet   0..1   gpu:16GB      on-demand  *             -        active  10 min ago
```

</div>

**Step 3: run evaluation or training loops as tasks**

Tasks are the batch form: training runs, eval runs, data processing. 

```yaml
# train.dstack.yml
type: task
name: train-qwen

image: huggingface/trl-latest-gpu
working_dir: /workspace

files:
  - .:/workspace

commands:
  - pip install -r requirements.txt
  - python train.py --model Qwen/Qwen2.5-7B-Instruct --output-dir /workspace/checkpoints

max_duration: 2h
resources:
  gpu: 24GB
  shm_size: 16GB
```

Tasks can be distributed (`nodes` set to a number), in which case `dstack` handles cluster selection and job coordination across nodes.

Once a task is running, the agent may attach to it and SSH inside the container to run commands interactively, or inspect runtime state before deciding what to do next.

<div class="termy">

```shell
$ dstack attach train-qwen --logs
```

</div>

<div class="termy">

```shell
$ ssh train-qwen
```

</div>

**Step 4: run model inference as services**

Services are the inference form: they turn a model into a endpoint that later steps in the loop can call, monitor, and scale as needed.

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
model: Qwen/Qwen2.5-32B-Instruct
replicas: 1..4
scaling:
  metric: rps
  target: 10

resources:
  gpu: 80GB
  disk: 200GB
```

Once the service is running, the endpoint can be called directly, including from another agent step:

<div class="termy">

```shell
$ curl https://qwen25-instruct.example.com/v1/chat/completions \
   -H 'Content-Type: application/json' \
   -H 'Authorization: Bearer <dstack token>' \
   -d '{
     "model": "Qwen/Qwen2.5-32B-Instruct",
     "messages": [{"role": "user", "content": "Hello"}]
   }'
```

</div>

This matters because the agent does not just launch the service. It can treat the endpoint itself as part of the workflow: deploy it, call it, monitor it, and adjust it through the same orchestration layer.

**Step 5: observe through events and metrics**

`dstack` exposes structured lifecycle data through events and metrics, so the loop can inspect state transitions and resource usage directly instead of inferring everything from logs.

<div class="termy">

```shell
$ dstack event --within-run train-qwen

 [2026-01-21 13:09:37] [run train-qwen] Run submitted. Status: SUBMITTED
 [2026-01-21 13:09:57] [job train-qwen-0-0] Job status changed SUBMITTED -> PROVISIONING
 [2026-01-21 13:11:49] [job train-qwen-0-0] Job status changed PULLING -> RUNNING
```

</div>

<div class="termy">

```shell
$ dstack metrics train-qwen

 NAME        STATUS   CPU  MEMORY       GPU
 train-qwen  running  92%  118GB/200GB  gpu=0 mem=71GB/80GB util=97%
```

</div>

Taken together, these are the fine-grained primitives a fully autonomous agent needs: discover capacity, provision it, run the right workload type, inspect state, and decide what to do next without handing orchestration back to a human operator.

## Skills

Those primitives make orchestration operable by agents, but they do not encode all of the workload-specific know-how. Training recipes, inference tuning, eval patterns, and runtime trade-offs still need to live somewhere.

`dstack` already ships an installable [SKILL.md](https://skills.sh/dstackai/dstack/dstack) so tools like Claude Code, Codex, Cursor, and others can learn how to operate `dstack` configs and CLI without guessing:

<div class="termy">

```shell
$ npx skills add dstackai/dstack
```

</div>

Skills are the layer where that operational know-how can be packaged and reused.

> The orchestrator provides the control surface. Skills provide the workload knowledge on top of it.

## Why open source and the ecosystem matter here

Once orchestration becomes the interface that agents use, ecosystem depth matters for both sides.

Teams want a control plane they can inspect and extend because it sits in the path of cost, reliability, and security. Providers want their capacity to be usable through standard patterns instead of one-off glue. Open source accelerates both: more backends, more integrations, more operational recipes, and fewer bespoke adapters per provider or per team.

`dstack` is MPL-2.0 licensed. That matters because agentic orchestration will not be built once inside a single vendor boundary; it will be assembled across GPU clouds, Kubernetes, on-prem infrastructure, and a growing ecosystem of specialized operational patterns.

## What's next

Agentic engineering is moving toward agents that own execution, not agents that merely assist humans during execution. If training jobs, evaluations, and inference services are part of execution, then GPU orchestration has to be part of what agents can operate directly.

If you want to use `dstack` for these workflows or contribute to the surrounding ecosystem, issues and feedback are welcome in the [GitHub repo](https://github.com/dstackai/dstack).
