# Preset requirements interview

Turn what the user needs from a model endpoint into a `preset.dstack.yml` they have
confirmed. The user describes requirements in plain language; you write the YAML. Once
creation starts, the configuration is frozen (`dstack preset resume` keeps the original),
so every requirement must be settled before `dstack apply`.

## 1. Collect what is already known

Before asking anything, build a fact table from:

- The user's request and any files they referenced (an existing `*.dstack.yml`, a service
  configuration they run today, benchmark results, traffic numbers).
- `dstack fleet` and `dstack fleet get <fleet> --json`: the fleets and the GPUs they
  actually have.
- `dstack offer --fleet <fleet> --group-by gpu`: what the fleet can provision.
- `dstack preset list -a`: earlier presets for the same model, candidates for `previous`.

Record only facts the user stated or a file or command proves, and note the source of
each. Do not fill gaps with values from a model card, a recipe, or a framework default.

## 2. Ask once, in one grouped turn

Ask only for required facts that are still unknown or contradictory. Put every question
in a single concise message; a question that first comes up after creation started is an
interview defect. For each question, propose a value when you have grounds for one and
say in a few words why it matters. Use a multiple-choice question tool only for bounded
choices, such as the workload profile or `base` vs `repo`. Accept natural-language
answers; never make the user write YAML. Never ask for secret values: only the names of
environment variables, such as `HF_TOKEN`.

Do not add a confirmation round for a value the user already stated unambiguously.

### Required

| Fact | Field | What to clarify |
| --- | --- | --- |
| Model | `base` or `repo` | `base` lets the agent pick another precision, quantization, or fork; `repo` pins the exact weights. Ask whether a quantized variant is acceptable for their quality bar. |
| Hardware | `fleets` or `--fleet` | The fleet must contain exactly the hardware the preset should run on; the agent may use anything the fleet offers. |
| Workload shape | `input_tokens`, `output_tokens`, `shared_prefix_tokens`, or `dataset` | Typical prompt and completion length, and how much of each prompt is identical across requests (system prompt, tool definitions, conversation history). |
| Load | `concurrency` | Simultaneous requests per replica. |
| Latency limit | `max_ttft` | p50 time to first token in milliseconds. |
| Context | `min_context_length` | The longest request the endpoint must accept, prompt plus output. |
| Effort | `trials` | How many benchmarked trials to run. More trials find more, but take longer and cost more. |

### Optional

- `agent`: provider, model, and effort for the creation agent.
- `previous`: earlier sessions to build on.
- `baseline`: `false` to skip the framework-defaults baseline trial.
- `env`: names of environment variables the runs need, e.g. `HF_TOKEN` for gated models.
- `gateway`.
- Preferences for `prompt`: frameworks or variants to try, what must not change, how
  deep to go.

### When the user doesn't know the workload

Never fall back to the silent `1024`/`1024` default. Offer a profile, adjust it with the
user, and record the resulting numbers:

| Profile | `input_tokens` | `output_tokens` | `shared_prefix_tokens` |
| --- | --- | --- | --- |
| Chat assistant | 2000 | 500 | 1000 |
| RAG or document Q&A | 8000 | 500 | 1000 |
| Coding or tool-using agent | 32000 | 1000 | 28000 |
| Summarization | 8000 | 1000 | 0 |
| Reasoning | 1000 | 8000 | 0 |

If the user has real traffic that matches a dataset the benchmark tool supports or a
Hugging Face dataset, prefer `dataset`; it excludes the three token fields.

### When the user describes the whole deployment

If load is given as requests per second, active users, or totals across replicas, derive
per-replica `concurrency` explicitly (e.g. by Little's law: request rate times mean
request duration, divided by replicas), show the arithmetic, and confirm it.

## 3. Check feasibility

Before writing the configuration, check and report any conflict to the user instead of
silently resolving it:

- The model weights in the intended precision, plus KV cache for `concurrency` requests
  at the expected lengths, fit the GPU memory of the fleet.
- `min_context_length` does not exceed the model's maximum context length.
- `max_ttft` is plausible for prefilling `input_tokens` (minus `shared_prefix_tokens`
  when it is cached) on that hardware at that concurrency.
- The fleet exists and `dstack offer --fleet <fleet>` returns offers.
- `shared_prefix_tokens` is less than `input_tokens`, and `dataset` is not combined with
  the token fields.

## 4. Flag what presets cannot enforce

The creation agent maximizes output token throughput at the single `concurrency`, and
enforces only p50 `max_ttft` and `min_context_length` as hard limits. When the user
states one of the following, tell them it is not enforced. If it can be expressed as
guidance, put it in `prompt` and say that the agent treats it as a hint, not a check:

- Other latency limits: p90/p99 TTFT, time per output token, inter-token latency,
  minimum tokens per second per user, end-to-end latency.
- Several concurrency levels, a concurrency range, or a request rate. Pick the single
  concurrency that matters most, or create one preset per level.
- Cost: throughput per GPU or per dollar, or a GPU count cap. The agent may use any
  hardware the fleet allows, so restrict the fleet to the intended GPUs instead.
- A quality bar for quantized or forked variants. Use `repo` to pin exact weights when
  quality must not change.
- Required serving features: tool calling, reasoning output, structured output,
  multimodal input, LoRA adapters.
- Fixed choices: a framework, an image, no source patches, a parallelism layout.
- Beating the user's current deployment. `baseline` always means the framework's
  recommended defaults; describe the current deployment in `prompt`.
- A local trace file, request length distributions, or multi-turn sessions.
- A wall-clock or cost budget for the creation itself. Only `trials` bounds it.

## 5. Write and confirm

Write `preset.dstack.yml` with the hard constraints from the interview. Show it to the
user together with:

- the derived values and the arithmetic behind them,
- any assumption the user deferred,
- the requirements that are not enforced (from step 4).

Run `dstack apply -f preset.dstack.yml` only after the user explicitly accepts this
configuration. Silence, a partial answer, or general enthusiasm is not acceptance. If the
user changes a requirement after creation started, create a new preset, passing the
interrupted one in `previous`.
