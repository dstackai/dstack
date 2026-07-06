# examples-llm-deployments

## Summary
The repo's LLM serving examples now live primarily as YAML embedded in mkdocs docs pages (mkdocs/docs/examples/inference/{vllm,sglang,trtllm,nim,dynamo}.md); the examples/ directory itself contains only ONE serving .dstack.yml (examples/models/gpt-oss/amd/120b.dstack.yml). All examples are plain `type: service` configs using image + commands + port + model + env + volumes + resources.gpu; none use spot_policy. A preset-like mechanism ALREADY EXISTS: a "UI templates" system (core/models/templates.py UITemplate, server/services/templates.py, routers/templates.py) that pulls template YAMLs from a git repo (DSTACK_SERVER_TEMPLATES_REPO or per-project templates_repo) with an embedded `configuration: Dict[str, Any]` — a strong precedent/reuse candidate for endpoint presets. No "preset" or "recipe" concept exists anywhere in src/.

## Key files
- mkdocs/docs/examples/inference/vllm.md —  — vLLM service YAML (NVIDIA + AMD tabs), Qwen/Qwen3.6-27B on vllm/vllm-openai:v0.19.1
- mkdocs/docs/examples/inference/sglang.md —  — SGLang YAML incl. replica-groups PD-disaggregation example with `replicas: [{count, commands, resources, router|scaling}]`
- mkdocs/docs/examples/inference/nim.md —  — NIM YAML: registry_auth with NGC_API_KEY, no commands (image entrypoint), gpu: H100:80GB:8
- mkdocs/docs/examples/inference/trtllm.md —  — TensorRT-LLM YAML: trtllm-serve, gpu: H100:8
- mkdocs/docs/examples/inference/dynamo.md —  — Dynamo PD-disaggregation with replica groups + scaling (metric: rps)
- examples/models/gpt-oss/amd/120b.dstack.yml —  — Only real serving .dstack.yml file in examples/; vLLM on MI300X:8, env includes HF_TOKEN
- src/dstack/_internal/core/models/templates.py — UITemplate, AnyUITemplateParameter — Existing template model: type: template, name, title, description, parameters[], configuration: Dict[str,Any]
- src/dstack/_internal/server/services/templates.py — list_templates(project), _fetch_templates_repo, TEMPLATES_DIR_NAME='.dstack/templates' — Clones/pulls a git repo into SERVER_DATA_DIR_PATH/templates-repos/<key>, parses YAML templates, TTLCache 180s
- src/dstack/_internal/server/routers/templates.py — POST /api/project/{project_name}/templates/list — UI-facing list endpoint, ProjectMember permission
- src/dstack/_internal/server/settings.py — SERVER_TEMPLATES_REPO (line 145) — env var DSTACK_SERVER_TEMPLATES_REPO; per-project override via ProjectModel.templates_repo
- mkdocs.yml —  — nav lines 329-334 index Inference examples (SGLang, Dynamo, vLLM, NIM, TensorRT-LLM); many redirects show examples were moved from examples/ into docs

## Details
## 1. Where LLM serving examples live

The `examples/` directory was heavily trimmed. Current top-level dirs: `distributed-training, llms, misc, models, plugins, server-deployment, single-node-training`. The ONLY serving `.dstack.yml` on disk is `examples/models/gpt-oss/amd/120b.dstack.yml` (vLLM/ROCm). `examples/llms/deepseek/trl/*` are training tasks, not services. There are no per-example README.md files for inference in examples/ (READMEs exist only for misc/, plugins/, qlora, cloudformation).

The canonical serving examples are YAML blocks embedded in markdown under `mkdocs/docs/examples/inference/`:
- `vllm.md` — vLLM (NVIDIA H100:4 + AMD MI300X:4)
- `sglang.md` — SGLang (incl. replica-groups PD disaggregation)
- `trtllm.md` — TensorRT-LLM
- `nim.md` — NVIDIA NIM
- `dynamo.md` — Dynamo (PD disaggregation, autoscaling)
Also `mkdocs/docs/examples/models/{deepseek-v4.md, qwen36.md}` and `mkdocs/docs/examples/accelerators/*.md`.

Indexing: `mkdocs.yml` nav lines 316-341 (Examples > Training/Clusters/Inference/Models/Accelerators) plus a hand-written card grid in `mkdocs/docs/examples.md`. No metadata files. There is no TGI service example anymore (TGI appears only in the proxy model-client `src/dstack/_internal/proxy/lib/services/model_proxy/clients/tgi.py`, `format: tgi` in the model spec).

## 2. Representative full YAMLs (verbatim from repo)

vLLM (mkdocs/docs/examples/inference/vllm.md, NVIDIA tab):
```yaml
type: service
name: qwen36
image: vllm/vllm-openai:v0.19.1
commands:
  - |
    vllm serve Qwen/Qwen3.6-27B \
      --host 0.0.0.0 \
      --port 8000 \
      --tensor-parallel-size $DSTACK_GPUS_NUM \
      --max-model-len 262144 \
      --reasoning-parser qwen3
port: 8000
model: Qwen/Qwen3.6-27B
volumes:
  - instance_path: /root/.cache
    path: /root/.cache
    optional: true
resources:
  shm_size: 16GB
  gpu: H100:4
```
AMD variant differs only in image (`vllm/vllm-openai-rocm:v0.19.1`) and resources (`cpu: 52..`, `memory: 896GB..`, `disk: 450GB..`, `gpu: MI300X:4`).

SGLang (sglang.md, NVIDIA): same shape with `image: lmsysorg/sglang:v0.5.10.post1`, `commands: sglang serve --model-path Qwen/Qwen3.6-27B --tp $DSTACK_GPUS_NUM ...`, `port: 30000`, `model: Qwen/Qwen3.6-27B`, same cache volume, `resources: {shm_size: 16GB, gpu: H100:4}`.

NIM (nim.md) — no commands, uses registry_auth + env passthrough:
```yaml
type: service
name: nemotron120
image: nvcr.io/nim/nvidia/nemotron-3-super-120b-a12b:1.8.0
env:
  - NGC_API_KEY
registry_auth:
  username: $oauthtoken
  password: ${{ env.NGC_API_KEY }}
port: 8000
model: nvidia/nemotron-3-super-120b-a12b
volumes:
  - instance_path: /root/.cache/nim
    path: /opt/nim/.cache
    optional: true
resources:
  cpu: x86:96..
  memory: 512GB..
  shm_size: 16GB
  disk: 500GB..
  gpu: H100:80GB:8
```

Real on-disk example `examples/models/gpt-oss/amd/120b.dstack.yml` uses `env: [HF_TOKEN, MODEL=openai/gpt-oss-120b, VLLM_ROCM_USE_AITER=1, ...]` (HF_TOKEN as passthrough), short-form volume `- /root/.cache/huggingface:/root/.cache/huggingface`, `gpu: MI300X:8`.

Fields observed across all serving examples: `type: service`, `name`, `image`, `commands` (multiline `|` blocks), `port`, `model` (plain HF model-id string), `env` (list; passthrough names like `HF_TOKEN`/`NGC_API_KEY` and `KEY=value` pairs), `volumes` (instance_path/path/optional or short form), `resources` (`gpu: <NAME>:<count>`, `gpu: H100:80GB:8` with mem, ranges `cpu: 96..`, `memory: 512GB..`, `disk:`, `shm_size:`), `registry_auth`. Advanced: `replicas` as a LIST of replica groups `{count: 1 or 1..4, commands, resources, scaling: {metric: rps, target: 3}, router: {type: sglang}}` (sglang.md line ~155, dynamo.md line 27). `spot_policy` appears in NO example (only in concepts/services.md docs, values `spot|on-demand|auto`). Simple scalar `replicas: N` + `scaling` also documented in sglang/dynamo autoscaling notes.

## 3. Existing preset/recipe/template machinery

- "preset"/"recipe": do not exist as concepts anywhere in src/ (grep hits for those words are incidental — e.g. nebius "preset" is a cloud API field, runpod/cloudrift "template" is provider API terminology).
- "template" DOES exist as a real feature: **UI Templates** (added Mar 2026, migration `03_06_1200_a13f5b55af01_add_projectmodel_templates_repo.py`).
  - Model: `UITemplate` in `src/dstack/_internal/core/models/templates.py:59` — `{type: "template", name, title, description, parameters: List[AnyUITemplateParameter], configuration: Dict[str, Any]}` where `configuration` is a raw dstack run configuration dict. Parameter types: name, ide, resources, python_or_docker, repo, working_dir, env (with title/name/value).
  - Service: `src/dstack/_internal/server/services/templates.py` — `async list_templates(project) -> List[UITemplate]`; clones a git repo (`project.templates_repo` or `settings.SERVER_TEMPLATES_REPO` = env `DSTACK_SERVER_TEMPLATES_REPO`, settings.py:145) into `SERVER_DATA_DIR_PATH/templates-repos/<md5 key>`, reads YAML files from `.dstack/templates` dir in the repo, TTL-cached 180s, run in thread via `run_async`.
  - Router: `src/dstack/_internal/server/routers/templates.py` — `POST /api/project/{project_name}/templates/list`, `ProjectMember()` permission, registered in `server/app.py`.
  - DB: `ProjectModel.templates_repo` column in `server/models.py`.
  - These templates are consumed by the UI only; there is no server-side "instantiate template into a run" logic in src/.

## 4. Preset sketch grounded in real syntax

A preset could be a stored service config keyed by model + accelerator, e.g.:
```yaml
# preset for Qwen/Qwen3.6-27B on NVIDIA
model: Qwen/Qwen3.6-27B
service:            # verbatim dstack service configuration (like UITemplate.configuration)
  type: service
  image: vllm/vllm-openai:v0.19.1
  commands:
    - |
      vllm serve Qwen/Qwen3.6-27B --host 0.0.0.0 --port 8000 \
        --tensor-parallel-size $DSTACK_GPUS_NUM --max-model-len 262144
  port: 8000
  model: Qwen/Qwen3.6-27B
  env:
    - HF_TOKEN        # passthrough, merged with endpoint's env
  volumes:
    - instance_path: /root/.cache
      path: /root/.cache
      optional: true
  resources:
    shm_size: 16GB
    gpu: H100:4       # matching key vs fleet GPUs
```
Every field above is verified real service syntax. The existing UITemplate pattern (raw `configuration: Dict[str, Any]` validated later against the run-configuration parser) is the natural precedent for storing the embedded service config.

## Gotchas
1) Do NOT assume examples/ contains vLLM/SGLang/TGI .dstack.yml files — it doesn't; the serving YAMLs live only inside mkdocs markdown, so a preset library cannot be built by globbing examples/. 2) There is no TGI serving example anymore (TGI survives only as a proxy model `format`). 3) `replicas` in current examples is a LIST of replica-group objects (count/commands/resources/scaling/router), not just an int — a preset schema must allow both. 4) `model:` in service YAML is a plain string (HF model id); older `model: {type/name/format}` object form was not seen in these examples. 5) No example uses spot_policy; don't copy it into presets as if idiomatic. 6) An existing "templates" feature (UITemplate + git-repo fetch + /templates/list API) already occupies the template namespace — the endpoint plan should either reuse it or deliberately name presets differently to avoid collision. 7) GPU spec strings like `H100:80GB:8` and range syntax `cpu: 96..` / `memory: 512GB..` are valid and used; presets should preserve exact string forms.
