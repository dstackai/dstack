# dstack-prototyping Skill Scorecard

Score every bullet from 0 to 10. Each bullet should stand alone and cover one complete idea.

- Purpose: use this skill to find a working dstack service recipe for a requested model by testing the recipe in a task on real hardware before submitting the final service.
- Dependency: this skill must be used together with the `dstack` skill; `dstack` provides CLI/YAML syntax, while this skill explains how to prototype model serving with dstack runs.
- Fleet/backend choice: prefer allowed fleets/backends that can leave an idle instance available after a run so repeated task/service attempts can reuse the provisioned machine and local caches, especially model weights; judge this from fleet config, current fleet state, backend docs, and observed run behavior, not from price alone.
- Interactive access: attach, SSH, or Kubernetes exec is useful for inspecting and adjusting a live task, but it is separate from idle instance reuse; prefer both when available.
- Serving sources: check serving-framework sources early enough to choose image, command, flags, resources, cache paths, request format, and expected model behavior; for vLLM and SGLang, treat the listed recipe/docs/cookbook sources as credible starting points.
- Task workflow: before submitting a service, start a long-lived task with `sleep infinity` or equivalent, attach/SSH when available, and test image, installs, model download/cache, serving command, port, launch flags, local model request, and expected model behavior; if image, hardware, or install path changes, submit another task.
- Service workflow: submit the service after the task verifies the recipe, then repeat the model request through the dstack service URL; if the fix requires changing image/install/download/command/resources/cache/model behavior, return to a task, otherwise fix and resubmit the service config.
