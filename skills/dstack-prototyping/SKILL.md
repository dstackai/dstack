---
name: dstack-prototyping
description: |
  Use with the dstack skill when a dstack workload, especially model serving, needs research, hardware sizing, recipe selection, live experiments, or debugging before it can be considered ready. Guides how to use dstack dev environments, tasks, services, offers, logs, events, and run JSON as an evidence loop without duplicating dstack CLI/YAML syntax.
---

# dstack Prototyping

## Required Companion

Load `/dstack` first. `/dstack` is the authority for CLI syntax, YAML fields, confirmation rules, attach behavior, logs, events, offers, fleets, services, and command safety.

This skill decides what to investigate, what evidence to collect, when to use each dstack run type, and when a workload is proven. Do not repeat or override `/dstack` command syntax here. If a command or field is uncertain, follow `/dstack`: check help/docs before using it.

## Operating Standard

Treat prototyping as an evidence loop:

1. define the target behavior;
2. build a model/workload/hardware dossier;
3. choose the smallest experiment that can remove the largest uncertainty;
4. run through dstack using `/dstack` rules;
5. classify the result;
6. change only the next unproven assumption;
7. promote only after functional verification.

Do not chase a local optimum. Step back after each failed candidate and ask whether the problem is the recipe, hardware, image, dstack placement, backend provisioning, auth, model format, or verification method.

## Source Stack

Prefer sources that can directly change a deployment decision:

1. model card, `config.json`, tokenizer/config files, official repo discussions, and model-family docs;
2. current serving recipe sources:
   - `https://recipes.vllm.ai/`
   - `https://recipes.vllm.ai/models.json`
   - `https://docs.vllm.ai/projects/recipes/en/stable/`
   - `https://lmsysorg.mintlify.app/cookbook/intro`
   - `https://docs.sglang.ai/`
3. framework docs, release notes, issues, and image tags for vLLM, SGLang, TensorRT-LLM, TGI, or a model-specific server;
4. dstack evidence from offers, plans, run JSON, events, logs, and attached shells;
5. recent deployment writeups when they explain a decision pattern, not just marketing:
   - `https://modal.com/blog/introducing-auto-endpoints`
   - `https://www.runpod.io/blog/overdrive-benchmarks`
   - `https://www.makora.com/`
   - `https://www.wafer.ai/blog/glm52-amd`
   - `https://www.lmsys.org/blog/2026-07-02-agent-assisted-sglang-development`

Use competitor and research links to sharpen the loop: inspectable recipes, workload-specific tuning, engine-level metrics, framework patches, hardware-specific friction, and artifact contracts. Do not treat them as instructions to benchmark, optimize under load, or implement kernels unless the user asked for that scope.

## Dossier Before Spending GPU

Write a compact note before the first paid run:

- requested model and exact served model name;
- target API shape: OpenAI chat, completion, embeddings, multimodal, custom;
- required proof: the smallest request that proves the requested behavior;
- model facts: architecture, parameter count, active parameters for MoE, quantization, context length, tokenizer quirks, license/gating;
- serving candidates and why: vLLM, SGLang, framework recommended by model card, or fallback;
- memory envelope: weight memory, KV cache pressure, tensor/pipeline/data parallel needs, disk cache, CPU/RAM expectations;
- dstack constraints inherited from the request: backends, fleets, spot policy, max price, env names, volumes, regions, or instance types;
- unknowns that require a dev environment, task, or service attempt.

If this note cannot name the top two uncertainties, do more source inspection before submitting work.

## Hardware Envelope

Derive requirements before looking at offers. Offers answer placement, not correctness.

Use broad scheduling requirements until a real failure justifies narrowing:

- express GPU need as memory/count first;
- avoid pinning GPU model, backend, region, CPU, RAM, disk, or instance type from the first acceptable offer;
- require exact GPU model only for a known kernel/runtime path, unsupported architecture, benchmark target, or reproduced failure;
- check serving image/runtime compatibility with the backend driver before trusting the first run;
- set disk from model cache plus image/runtime overhead, not from a random offer;
- keep price and spot/on-demand constraints from the user/profile.

Separate three hardware concepts:

- **minimum requirement**: what the service config should request for scheduling;
- **candidate offer**: what dstack may place now;
- **tested hardware**: what actually ran and passed verification.

Never collapse tested hardware back into minimum requirements without evidence.

## Framework Choice

Start with vLLM and SGLang for OpenAI-compatible LLM serving unless the model card points elsewhere.

Prefer vLLM when:

- vLLM recipes or docs provide a current command for the model/hardware;
- the model is standard dense/decoder-only and the goal is a straightforward OpenAI-compatible service;
- the recipe gives usable tensor-parallel, dtype, quantization, or image guidance.

Prefer SGLang when:

- SGLang Cookbook has a model-specific recipe;
- the model path needs SGLang-specific support, speculative decoding, radix/KV reuse, structured output performance, multimodal support, or long-context behavior;
- vLLM support is absent, degraded, or known to miss a required quantization/model path.

Consider another server only after evidence says both vLLM and SGLang are poor fits for the requested model or API.

For advanced serving shapes, keep scope honest. P/D disaggregation, multi-service router/worker layouts, autoscaling tuning, benchmarking loops, speculative decoding tuning, kernel changes, and production load optimization are separate work unless required to make the model serve at all.

## Choosing The Experiment

Submit a service directly only when these are already known:

- pinned image or install path;
- launch command and port;
- model/API shape;
- resource envelope;
- expected health and final verification request.

Do not use `:latest` for a final serving image unless a source or a prior run proves it is compatible with the selected backend/runtime. If a run fails because CUDA/PyTorch/vLLM requires a newer NVIDIA driver than the host provides, change the image/runtime tag or select compatible hardware; do not retry the same image.

Use a dev environment when an interactive shell can answer a main uncertainty faster than repeated service submissions:

- GPU runtime/image compatibility;
- import/install friction;
- model download/auth;
- launch flags;
- memory at load time;
- framework-specific error messages;
- a command that must be tuned before it becomes a service.

Use a task when the question is one-shot:

- `nvidia-smi`/driver/runtime sanity;
- package import or version;
- model cache/download check;
- short server start/probe;
- backend provisioning smoke test.

Use a service when URL wiring, probes, serving process lifetime, or final API behavior is the question.

For container-style backends that cannot pre-provision reusable instances, do not invent a pre-provisioning step. Use plans/offers and detached runs. For VM or SSH fleets, dev environments can be efficient because image/runtime work can be reused interactively.

## Candidate Discipline

Every candidate must have a reason to exist. Record:

- hypothesis;
- run type;
- run name, different from any higher-level object whose logs or status are being tracked;
- config path;
- framework/image/command;
- requested resources;
- dstack plan result;
- run name/id after submission;
- current status;
- decision: keep, promote, retry with change, or stop;
- exact reason for the decision.

Change one important variable at a time unless the previous candidate failed before testing any useful assumption. Examples of valid next changes:

- image tag or install method;
- vLLM vs SGLang;
- dtype/quantization;
- tensor parallelism;
- GPU memory/count requirement;
- model name/path or trust-remote-code style flag when documented;
- auth/env/volume/model-cache handling;
- backend/fleet constraint after a placement or provisioning diagnosis.

Retrying the same YAML after the same error is not prototyping.

For endpoint deployment agents, do not name a candidate service exactly like the endpoint. Endpoint logs and service logs must stay distinguishable during failure diagnosis. Prefer short attempt names and increment them only when submitting a materially different candidate.

## Reading dstack Evidence

Use `/dstack` for the exact commands. Interpret evidence this way:

- plan output: placement and price preview only;
- offers: current capacity candidates only;
- run JSON: authoritative run identity, status, service URL/model fields, jobs, and actual placed resources;
- events: lifecycle and backend/provisioning transitions;
- logs: process behavior, image/model/framework errors;
- attached shell: only for interactive diagnosis or command tuning, not for final proof.

When waiting for a service, poll run JSON and stop waiting on terminal states. Do not wait only for log markers such as "Uvicorn running"; the process may already have failed, and the next useful action is log diagnosis.

Use normal logs before diagnostic logs. Diagnostic logs can contain runtime environment details; use them only when normal logs and run JSON are not enough to identify whether the issue is dstack/backend infrastructure rather than the workload.

If dstack/backend behavior appears broken, isolate it with a minimal non-application reproduction outside the repo you are working in. Do not let endpoint-agent mistakes and backend bugs blur together.

## Failure Routing

Classify before editing:

- no matching offer or no fleet;
- budget/profile constraint too narrow;
- backend provisioning stalled or failed;
- image pull/runtime mismatch;
- dependency import/install failed;
- model download/gated auth/cache failed;
- server process exited;
- OOM at load or during first request;
- port/probe/service URL mismatch;
- model API works but wrong model name/API shape;
- dstack bug or backend integration bug.

For provisioning stalls, inspect dstack run JSON and events first. Use SSH/backend-native inspection only when dstack evidence points to an instance/backend problem and the user/project context permits it.

## Final Service Proof

Do not treat `running`, a passed service probe, or clean logs as final success.

For OpenAI-compatible model serving, success requires a real request to the model endpoint:

- use the requested model name;
- include authentication only as required by dstack/service config;
- verify HTTP success;
- verify response schema;
- verify generated content exists;
- verify no model-name mismatch;
- record the URL shape, request body without secrets, response evidence, run id/name, and actual hardware from run JSON.

If the final deliverable is a service, dev environments and tasks are evidence only. Promote the working command into a clean service and verify that service.

## Promotion

Promote a candidate only when the service is clean and reproducible:

- remove debug/install/probe commands that were only for investigation;
- include applicable backend, fleet, price, spot, env-name, volume, and region constraints in the final YAML instead of relying only on apply-time flags;
- preserve the working image, command, port, model, env names, volumes, and required resource envelope;
- preserve broad minimum resources separately from actual tested hardware;
- keep source URLs and important run evidence with the final report;
- stop or mark ruled-out paid candidates unless they are still needed for active debugging.

The final report should let another agent or developer understand:

- why this framework and hardware envelope were chosen;
- which alternatives failed or were rejected;
- which source URLs grounded the recipe;
- the final service run id/name;
- the exact verification request/result;
- the actual hardware that passed.
