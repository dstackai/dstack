# dstack CLI and Service Authoring

Core CLI rules:

- Preview before submit with `printf 'n\n' | dstack apply -f <config> ...`.
- Submit runs detached with `dstack apply -f <config> -y -d`.
- Never run `dstack apply` for a run without `-d` in this non-interactive server context.
- Do not use `dstack ps` table text for machine decisions; table output can be truncated. Use `dstack run get <run-name> --json` for machine decisions.
- Use `dstack event --within-run <run-name>` and `dstack logs <run-name>` to understand provisioning, pulling, startup, and runtime failures.
- A run can be `running` before the in-server proxy can answer. Before probing the service URL, check `dstack run get <run-name> --json` for a running job and HTTP probe state. If a probe has `success_streak > 0`, proceed to a real model request. Do not block on a `registered` field if it is absent or null.
- If a run is externally stopped or has `termination_reason: stopped_by_user`, do not resubmit it.
- Stop a bad candidate before replacing it: `dstack stop <run-name> -y`.
- Retry only after changing the underlying hypothesis, YAML, command, image, hardware, or constraints.

Service essentials:

- The final endpoint-backed YAML must be `type: service`; choose a concise, unique run name that is useful for debugging.
- The final service YAML must include `model: <requested model>` so dstack exposes a model URL.
- Services usually need `port: 8000` and commands that start an OpenAI-compatible server.
- Common starting points are `vllm serve <model>` and `python -m sglang.launch_server --model-path <model> --host 0.0.0.0 --port 8000`, but verify current docs and model-specific notes before trusting these defaults.
- Pass endpoint environment variables by name, for example `env: [HF_TOKEN]`; never write secret values into YAML or logs.
- Choose `resources` from evidence: model size, framework requirements, GPU memory, disk needed for weights/cache, and current dstack offers/fleets.
- Do not turn the first matching offer into the service requirements. Use offer previews to
  verify that the derived requirements are provisionable. Keep `resources` as ranges or
  minimums whenever that is enough for correctness.
- Do not pin `gpu.name`, `instance_types`, regions, CPU, memory, or disk from a preview
  offer unless there is a model/framework requirement or a documented provisioning reason.
  The actual instance that succeeds is recorded after provisioning, not guessed before it.
- For OpenAI-compatible verification, use `service.model.base_url` from `dstack run get <run-name> --json` and POST to `/chat/completions` with the requested model. If the base URL is relative, prefix it with the default project URL from `~/.dstack/config.yml`.
- After verification, read `dstack run get <run-name> --json` again and report actual
  provisioned hardware from the latest running job. If dstack fell back from one preview
  offer to another, the final report must name the hardware that actually ran.

Use dstack plans as real constraints. If the endpoint supplied `max_price`, `spot_policy`, backend, region, instance type, fleet, or reuse constraints, every offer lookup, preview, and submitted experiment must honor them.
