# Deployment Harness

Use this lifecycle:

1. Understand the model: source URLs, serving framework options, expected memory/disk, and any model-specific launch requirements.
2. Inspect project capacity: use `dstack offer` and/or existing fleets with the endpoint's binding constraints.
3. Pick the fastest credible experiment path:
   - If evidence is strong, preview and submit the final service candidate directly.
   - If startup commands, images, framework versions, or hardware are uncertain, prototype first.
   - Prototypes may be dstack services, tasks, or dev environments when that is the most effective way to test commands interactively.
4. Keep one active candidate at a time where possible. Stop bad candidates before replacing them.
5. Watch status using JSON run state, events, and logs. Use short probes and update workspace artifacts; do not hide progress inside long `sleep` or `until` loops.
6. When the final service reaches `running`, check `dstack run get <run-name> --json` for job status and probe state. A useful readiness signal is a running job with an HTTP probe `success_streak` greater than zero. Do not wait for a `registered` field if it is absent or null.
7. Get the model URL from `dstack run get <run-name> --json`, combine it with the configured server URL from `~/.dstack/config.yml` if it is relative, and send a real OpenAI-compatible chat request for the requested model.
8. Once the model request succeeds, write `verification.json`, write `final_report.json`, and return the structured final report immediately. Otherwise return a failed report with the useful evidence and the last candidate state.

Workspace artifact contract:

- On startup or resume, inspect `agent_state.json`, `candidates.jsonl`, `verification.json`, and `final_report.json` before submitting anything new. If a previous candidate is already running and verifiable, reuse it instead of creating a duplicate run.
- Keep `agent_state.json` current enough to show the phase.
- Add source evidence to `sources.jsonl`.
- Keep `hardware_reasoning.md` reviewable before any paid run.
- Record every spend-capable service, task, or dev-environment candidate in `candidates.jsonl`.
- The server records shell command/tool output in `commands.jsonl` and `command-output/`; use those artifacts when diagnosing.
- On success, write `verification.json` with the final model request evidence before returning the final report.
- Always write `final_report.json` before returning the structured final report.

Development environments and tasks are allowed for experimentation. Use them when they reduce uncertainty, for example to test an image, install path, model download, launch command, or framework compatibility before committing to the final service. They are not the endpoint: the final verified run reported to the server must be a dstack service.

For v1, do not attempt P/D disaggregation, router/worker multi-service topologies, autoscaling tuning, load benchmarking, or performance optimization unless they are strictly necessary to make the requested model serve at all. Note when those would be the right next step.

Hardware behavior:

- Do not blindly select the cheapest offer.
- Prefer hardware likely to run the serving image reliably: enough VRAM, enough disk, common CUDA-capable NVIDIA GPUs when using CUDA images, and offers without obvious provisioning instability.
- If a candidate stays in backend provisioning without logs/events progress after several polls, inspect run JSON/events and any available native backend or SSH/TCP evidence, then stop or fail with evidence rather than looping forever.
- If a backend or dstack provisioning issue is found, create or reference a minimal non-endpoint reproduction in `endpoint-agent-backend-troubleshooting.md` when possible.

Final report:

- On success, include the final service run id, final service run name, the exact final service YAML, recipe/source URLs, and a concise verification summary.
- On failure, include the failure summary and enough evidence for the next iteration to improve the harness.
