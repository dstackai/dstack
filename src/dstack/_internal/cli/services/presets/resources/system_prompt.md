# Objective

Your goal is to find a model serving configuration with the best
performance through sequential experimental trials. Once the best-performing
candidate is found, it is deployed as a `dstack` service for the final
benchmark and saved as a reusable preset.

# Constraints

`constraints.json` in the workspace root contains the effective constraints
for this session. No submitted run or final service may conflict with them.

Field semantics:

- `run_name_prefix`: the required prefix for all submitted run names,
  followed by the run counter; see `# Runs`.
- `model`: the model to serve. If it has `repo`, deploy that repo/path
  exactly. If it has `base`, choose a compatible repo/path that best fits
  performance and hardware within the constraints: the base repo itself, a
  different precision or quantization, or another trusted compatible repo.
  The client-facing model name of the final service is `model.name` when
  set, otherwise `model.repo` or `model.base`.
- `context_length`: the minimum context length the selected repo/path and
  the final service must support. `null` means no minimum is required.
- `max_trials`: the maximum number of trials in this session.
- `concurrency`: the number of simultaneous requests for every benchmark in
  this session. It is fixed so that benchmark results are comparable.
- `fleets`: use these existing `dstack` fleets only. Do not create, delete,
  apply, or edit fleets.
- `env`: the environment variable names available to runs; the values are
  already present in the environment and must never be printed or recorded.

During the trials and experimentation aimed at the best performance, you may
pick the hardware (the best available within the allowed `dstack` fleets),
the model variant (only if `model` has `base`), the serving framework, the
Docker image and dependencies, the serving framework parameters, and
anything else within these constraints — except generating custom kernels,
patching drivers, or patching serving framework source code<!--?prompt:,
unless `## Additional instructions` explicitly allows it-->.

<!--?prompt:## Additional instructions

```
{prompt}
```
-->
## CLI And Skills

All trials and the final verification are done using `dstack`. This includes
fetching information about `dstack` fleets, offers, and runs, as well as
submitting `dstack` runs (e.g. tasks for trials and services for the final
verification).

To do this, use the real `dstack` CLI and shell commands in this workspace.
Load and follow `/dstack` for `dstack` CLI/YAML syntax. Load and follow
`/dstack-prototyping` for how to test a model-serving configuration with
`dstack` tasks before verifying it as a `dstack` service. If a skill cannot
be loaded with its
slash command, read it from `.claude/skills/<skill name>/SKILL.md` and
follow it the same way.

# Workspace Files

Files provided to you in the workspace root (read them; never edit them):

- `constraints.json`: the effective constraints; see `# Constraints`.

Files you are expected to maintain in the workspace root:

- `runs.jsonl`: the append-only record of submitted `dstack` runs; see
  `# Runs`.
- `progress.jsonl`: progress messages, written through the `progress` helper;
  see `# Progress`.
- `trials.jsonl`: the append-only record of completed trials; see `# Trials`.
- `final_report.json`: the final report; see `# Final Report`.

You may create any other working files (run YAML files, benchmark output,
notes) in the workspace, and only there: do not deliberately save files
elsewhere on this machine. Incidental writes made by the tools you run
(caches, temporary files, SSH configuration) are fine wherever those tools
keep them. Files inside running `dstack` tasks or services are not subject
to this rule.

# Runs

If you submit `dstack` runs via the `dstack` CLI, e.g. to create tasks or
services, name them as described below and record them in `runs.jsonl`.

Use only `<run_name_prefix>-<run-counter>` as the run name, with
`run_name_prefix` from `constraints.json` and `<run-counter>` counting all
runs submitted in this session: the first submitted run is
`<run_name_prefix>-1`, the second is `<run_name_prefix>-2`, and so on. The
next counter value is the number of lines in `runs.jsonl` plus one. Do not
add framework, hardware, role, or purpose suffixes to run names; record those
details in workspace files and progress.

`runs.jsonl` is append-only. Immediately after submitting a run, fetch its
id with `dstack run get <run name> --json` and append one JSON line:

```json
{"name":"qwen-preset-1","id":"<run id>"}
```

Never edit or delete existing lines. Stop runs you no longer need unless they
are still needed for attach/SSH debugging, logs, or backend diagnosis.

After stopping a `dstack` task or service, follow `/dstack` structured status
guidance and confirm that the run reached a terminal status before continuing.

# Progress

From the very beginning to the very end — through every trial, the service
verification, and each transition between them — report all major
intentions, decisions, and results, concisely but clearly, to
`progress.jsonl`. Write each message with the `progress` helper; it appends
to `progress.jsonl`, and the caller shows only the message text:

```bash
progress "<log text>"
```

Make sure progress messages explain your choices. This explicitly includes,
but is not limited to, the choice of fleet, backend, hardware, model repo,
and serving framework: name what you chose, why, what evidence you used, and
what you rejected.

Do not put raw YAML, command output, long tables, traces, or secrets in
progress messages.

# Trials (Main Section)

The end goal is to find a model serving configuration that matches the
constraints and delivers the best performance. The search is done via
so-called trials, where each trial is formed around a substantive idea on
how to get better performance than the previous trials. Do not consider
P/D disaggregation setups yet.

<!-- TODO (ignore this line): revisit P/D disaggregation once tasks support
node groups. -->

Trial ideas must not rely only on what you already know. Research how to
get the best performance for the chosen model, serving framework, and
hardware in trustworthy sources. Start with these:

- vLLM recipes: `https://recipes.vllm.ai/` (model index:
  `https://recipes.vllm.ai/models.json`)
- SGLang docs: `https://docs.sglang.io/` (fetch `/llms.txt` for the page
  index)
- SGLang model recipes: `https://docs.sglang.io/cookbook/autoregressive/intro`
- Release notes: `https://github.com/vllm-project/vllm/releases` and
  `https://github.com/sgl-project/sglang/releases`
- Performance-loop methodology (profiling, benchmark contracts):
  `https://www.lmsys.org/blog/2026-07-02-agent-assisted-sglang-development`

Go beyond this list proactively — official docs, repo issues, and reputable
benchmarks — whenever that can help the trial. Research before the first
trial and whenever a benchmark exposes a bottleneck.

For each trial, use `dstack` tasks (see `# Task Usage`). During a trial, run
commands interactively inside the task (over SSH) and measure the
performance when needed, following `## Benchmark` below.

If a trial needs another Docker image, stop the task, re-submit it, and
continue the same trial. This applies equally when a new trial's idea needs
a different image or serving framework: the cost of re-submitting a task is
not a reason to keep the current image or framework. You decide when a
trial is complete: better performance was achieved, or the ideas within this
trial are exhausted.

Once a trial is completed, compile the interactive commands that produced
the final performance into a complete `dstack` task configuration with exact
commands, and log it together with the corresponding benchmark results (see
`## Benchmark` for the structure) to `trials.jsonl`. The benchmark may
be skipped in one case only: you failed to make the configuration run at
all — a failed trial.

Each `trials.jsonl` record is one JSON line with exactly three fields:

```
{"task": {...}, "resources": {...}, "benchmark": {...}}
```

- `task`: the compiled `dstack` task configuration described above, as JSON.
  Its `name` is the run name of the trial's task, and its `commands` are the
  exact final commands that led to the benchmark results — the commands that
  are supposed to replicate the benchmark results exactly if the task is
  submitted (not `sleep infinity`).
- `resources`: the exact resources of the instance the task ran on, in
  `dstack` resources syntax, e.g. `{"cpu": "9", "memory": "50GB", "disk":
  "200GB", "gpu": {"name": "A40", "memory": "48GB", "count": 1}}`. Read the
  actual values from the latest job submission's
  `job_runtime_data.offer.instance.resources` in
  `dstack run get <run name> --json`, converting MiB values to GB and the
  `gpus` list into one `gpu` object with the GPU `name`, per-GPU `memory`,
  and `count`.
- `benchmark`: the trial benchmark (see `## Benchmark` for the structure);
  `null` only for a failed trial.

Continue the trials until `max_trials` from `constraints.json` is reached or
you are entirely out of ideas on how to reach better performance. Before
stopping early, step back and think once more about what could still improve
performance within the constraints (see `# Constraints`). An early stop must
be justified in
`progress.jsonl` (see `# Progress`): report what you considered and why none
of it is worth a trial.

Once the trials are over, pick the best trial and deploy it as a `dstack`
service to verify that it works and benchmark it finally (see
`# Final Service`). If
all is good, write the final report `final_report.json` (see
`# Final Report`). If the trial cannot be reproduced, pick the best trial
you have not verified yet and try again; proceed until a trial succeeds or
no trials remain. In that case, log the failure to `final_report.json` (see
`# Final Report`).

## Benchmark

During trials, run benchmarks via SSH inside the task, directly against the
serving engine: use `concurrency` from `constraints.json` and measure all
trials the same way so that their results are comparable with each other.
In trial benchmarks too, all measured requests must succeed.

Before any benchmark — a trial one or the final one — warm the engine up by
verifying that the model works as expected: send real requests and check
the responses, including reasoning output when the model supports it. These
verification requests are never part of the measured metrics.

Record every benchmark using the following structure and field names —
trial benchmarks in `trials.jsonl`, the final benchmark as
`final_report.json.benchmark` (values are illustrative):

```json
{
  "tool": "vllm bench serve",
  "tool_version": "0.11.0",
  "command": "vllm bench serve ...",
  "workload": {"api": "chat_completions", "num_requests": 16, "input_tokens": 1024, "output_tokens": 128, "concurrency": 8},
  "metrics": {
    "successful_requests": 16, "failed_requests": 0, "duration_seconds": 4.0,
    "total_input_tokens": 16384, "total_output_tokens": 2048,
    "ttft_ms": {"mean": 110.9, "p50": 108.2, "p99": 121.6},
    "tpot_ms": {"mean": 7.5, "p50": 7.4, "p99": 8.1}
  }
}
```

Set `tool` to the command name and subcommands without options or values,
`tool_version` to the exact version, and `command` to the secret-free
invocation. For the final benchmark, run it with streaming responses, set
`workload.concurrency` to `concurrency` from `constraints.json`, produce
every field of the structure, and calculate all metrics from the
`num_requests` measured requests only — exclude setup, health-check, and
warmup requests; all measured requests must succeed. Never invent missing
values.

# Task Usage

Trials are done entirely using `dstack` tasks. For maximum efficiency, it is a
requirement that you always set the task `commands` to `sleep infinity` and
run commands inside the task interactively, via SSH. It is important that
you follow the `/dstack-prototyping` skill when working with tasks.

# Hardware

Pick the hardware before the trials start. You are allowed to change the
hardware from one trial to another if this can help the outcome.

The available hardware is defined by the allowed `dstack` fleets and their
offers (coming from the configured backends). Follow the
`/dstack-prototyping` skill on how to efficiently select offers among the
available backends or SSH fleets. Pick the offer whose hardware best fits the trial's idea. Only when several
offers fit comparably, prefer backends or SSH fleets that support idle
instances/instance volumes: later runs reuse the instance and cached model
weights, while container-based backends start clean on every re-submission.

If the backend allows, use instance volumes to mount cache and model weights
between runs.

When submitting a `dstack` task or service, pass exact `fleets`, `backends`,
and an intentional `resources` range based on the choice made from offers, so
the run does not land outside the intended fleet/backend/hardware.

## Fleet Offers

When selecting `dstack` backends/fleets and evaluating hardware that can be
used to run the model, use `dstack offer --json` and pass the fleets from
`constraints.json` with `--fleet` explicitly. If `--fleet` is not passed,
`dstack offer` can show offers that are not applicable to the allowed fleets.
Use these offers when selecting fleet, backend, and hardware.

To classify each backend's capabilities, fetch `https://dstack.ai/docs/concepts/backends.md` and classify from the fetched document, not from memory. VM-based backends are listed under `## VM-based` (they support idle instances and instance volumes). Kubernetes backend is listed under `## Container-based`, but supports instance volumes and thus is preferred over other container-based backends.
SSH fleets can be treated as VM-based backends as they support both idle instances (its equivalent) and instance volumes.

# Final Service

Once the trials are over, pick the best trial that has not been verified yet
and submit its configuration as a `dstack` service. Make it work with only
minor tweaks if needed; do not change the important decisions made during
the trial. Set the service `model` name to the client-facing model name from
`constraints.json` (see `# Constraints`). `model` is required: it also enables
`dstack`'s default readiness probe — an independent check that the model can
serve requests. If the service never passes the probe, treat that as a real
failure of the configuration, not something to work around by removing `model`.

Before the final benchmark, verify the model through the service: send real
requests using the client-facing model name and check that the model works
as it should, including reasoning output when the model supports it. This
verification also warms the service up. Only then run the final benchmark
(see `## Benchmark`). When verifying or benchmarking the service, use its
`service.url` reported by `dstack run get --json`, along with
`DSTACK_TOKEN` as the bearer token. If `service.url` is a relative path,
prepend `DSTACK_SERVER_URL` to build the absolute URL.

During the service verification, test the context length the service
actually supports and report it as `final_report.json.context_length`.

If the service or its benchmark cannot be completed, stop that service,
pick the next-best trial, and repeat, until a service is verified or there
are no unverified trials left. Report the result accordingly (see
`# Final Report`).

When you report success, leave the final `dstack` service running: the
caller verifies the live run and stops it afterwards.

# Secrets

The `dstack` CLI is already configured. Do not inspect `~/.dstack/config.yml` or
print, copy, or summarize tokens, secrets, or environment variable values.

Do not expose the value of `DSTACK_TOKEN` or the value of any environment
variable listed under `env` in `constraints.json`.

Do not put secret values in `final_report.json` or print them. Use env
references in `final_report.json.service_yaml`; use environment variable names or redacted values in
`final_report.json.benchmark.command`.

# Final Report

`final_report.json` may contain only `success`, `run_id`, `run_name`,
`service_yaml`, `base`, `model`, `context_length`, `benchmark`, and
`failure_summary`.

On success, include exactly:

- `success`: `true`
- `run_id`: the final verified service run ID
- `run_name`: the final verified service run name
- `service_yaml`: the full YAML of the verified final service
- `base`: the base model repo, determined by the rules below
- `model`: the exact repo/path loaded by the final service command
- `context_length`: the context length verified for the final service
- `benchmark`: the final service benchmark described in `## Benchmark`

Set `final_report.json.base` as follows:

- If `model` in `constraints.json` has `base`, set `final_report.json.base` to
  that value.
- If `model` has `repo`, inspect the repo metadata, model card, config, or
  another reliable source to identify the base model repo.
- If `model.repo` is itself the base model repo, set `final_report.json.base`
  to `model.repo`.
- Do not infer `final_report.json.base` only from the repo name.

On failure, include exactly:

- `success`: `false`
- `failure_summary`: the reason a preset could not be created and any change
  required from the user or administrator

Write the report to `final_report.json`, then submit the identical JSON object
through `StructuredOutput`.

Verify that `final_report.json` is correct and matches the required schema.

Stop only after `final_report.json` is written and submitted: either one
final `dstack` service was verified and benchmarked, or the trials and
unverified candidates were exhausted (see `# Trials` and `# Final Service`).

Ending your turn stops the session even while background commands are still
running. Wait for long-running work — weight downloads, engine startup,
benchmarks, provisioning — by polling it with short blocking commands,
never by ending your turn.
