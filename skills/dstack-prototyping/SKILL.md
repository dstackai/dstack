---
name: dstack-prototyping
description: |
  Use with the dstack skill for model-serving work when the image, serving command, resources, backend/fleet choice, or service behavior is not proven. Guides task-first prototyping on real hardware, choosing fleets/backends that can reuse idle instances and caches, checking vLLM/SGLang sources, and verifying the final dstack service with a model request.
---

# dstack Prototyping

Use `/dstack` for CLI commands, YAML fields, apply/attach behavior, service URLs,
and other dstack syntax. This skill explains how to use dstack runs while the
model-serving recipe is still unknown.

## Goal

Find a working dstack service recipe for the requested model.

Before submitting a service, use a task on real hardware to test the serving
image, install/runtime assumptions, model download, cache path, command, port,
launch flags, resources, env vars, backend/fleet choice, and local model
request. Then submit the same recipe as a service and verify the model through
the dstack service URL.

## Choose Where To Run

Choose only VM-based backends, SSH fleets, or Kubernetes fleets because they support idle instances and/or instance volumes. That lets later runs reuse the provisioned/idle instance or instance volumes used by runs for caching model weights (and possibly other writes). You must follow this rule even if there are fleets/backends/offers that are cheaper. The only exception from this rule is when the required GPU class (regardless of the price) is not available through VM-based backend, SSH fleet, or Kubernetes fleet.

Read `https://dstack.ai/docs/concepts/backends.md` to know exactly which
backends are VM-based.

## Check Serving Sources

Check serving-framework sources early enough to choose the image, command,
launch flags, resources, cache paths, request format, and expected model
behavior.

For vLLM and SGLang, use these as credible sources:

- vLLM recipes and model index: `https://recipes.vllm.ai/` and
  `https://recipes.vllm.ai/models.json`
- vLLM recipe docs: `https://docs.vllm.ai/projects/recipes/en/stable/`
- SGLang docs and cookbook: `https://docs.sglang.ai/` and
  `https://lmsysorg.mintlify.app/cookbook/intro`

Use deeper serving-engine writeups, such as
`https://www.lmsys.org/blog/2026-07-02-agent-assisted-sglang-development`, when
recipes and docs do not explain the model, hardware, or serving failure.

## Use A Task Before Service

Before submitting a service, start a long-lived task:

```yaml
commands:
  - sleep infinity
```

or an equivalent idle command.

Submit the task detached, attach or SSH into it when available, and run commands
inside the live environment. Test the image, installs, model download and cache
path, serving command, port, launch flags, local model request, and expected
model behavior.

If the image, hardware choice, or major install path changes, submit another
task so the changed setup is tested before service verification.

Do not move to a service after checking only GPU visibility, imports, logs, or a
health endpoint. Start the server inside the task and send a request that uses
the requested model. For a chat or reasoning model, check the response behavior
the endpoint is expected to support, such as reasoning output when that model is
supposed to expose it.

## Verify As A Service

Submit the service after the task has verified the recipe: image, command, port,
resources, env vars, cache mounts if used, backend/fleet choice, and model
request.

Use the service as a duplicate check of the same recipe under dstack service
runtime. The model request that worked locally in the task must also work
through the dstack service URL.

If service verification fails because the image, install, model download,
command, resources, cache, or model behavior needs to change, go back to a task.
If the recipe is still right and only the service config is wrong, fix the
service config and submit the service again.
