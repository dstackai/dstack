# external-recipes

## Summary
Both projects exist and are Apache-2.0 licensed, so an embedded dstack agent can fetch, vendor, or redistribute their content with attribution. The SGLang Cookbook's canonical home is now docs.sglang.io/cookbook (source: sgl-project/sglang repo under docs_new/cookbook, MDX files); the old sgl-cookbook GitHub repo was archived read-only on 2026-06-11 and cookbook.sglang.io is legacy. vLLM recipes live at github.com/vllm-project/recipes and render at recipes.vllm.ai, which exposes a purpose-built machine-readable JSON API (/models.json index + per-model JSON with exact vllm serve commands, docker commands, and per-GPU hardware configs) — ideal for runtime WebFetch by an agent. SGLang has an llms.txt full-doc index at docs.sglang.io/llms.txt and serves page source by appending .md, but pages are MDX mixing static serve commands/hardware tables with JSX config-generator components, so parsing is messier; for SGLang, vendoring/sparse-cloning docs_new/cookbook or the archived repo's markdown is more robust.

## Key files
- https://recipes.vllm.ai/models.json —  — EXTERNAL URL (no local files in this research). Verified machine-readable index of ~500 model entries; fields per entry: hf_id, title, provider, url, json (path to per-model JSON), optional derived_from.
- https://recipes.vllm.ai/Qwen/Qwen3-32B.json —  — EXTERNAL URL. Verified per-model JSON: meta (title/description/hardware verification), model (parameter_count, context_length, min vLLM version), recommended_command (exact vllm serve string per hardware), docker_command (vllm/vllm-openai:latest), by_hardware map (H200/H100/B200/TPU), variants (BF16/FP8/AWQ), guide section.
- https://github.com/vllm-project/recipes —  — EXTERNAL URL. Canonical vLLM recipes repo, Apache-2.0 (LICENSE verified raw). New format: structured YAML at models/<hf_org>/<hf_repo>.yaml mirroring HuggingFace paths; legacy markdown per org (Qwen/Qwen3.5.md, GLM/GLM5.md, Google/Gemma4.md) still present but being migrated. JSON API rebuilt via scripts/build-recipes-api.mjs.
- https://raw.githubusercontent.com/vllm-project/recipes/main/models/deepseek-ai/DeepSeek-V4-Pro.yaml —  — EXTERNAL URL. Verified concrete YAML recipe: model_id deepseek-ai/DeepSeek-V4-Pro (1.6T MoE/49B active, 1,048,576 ctx), verified hardware matrix (H200/B200/B300/GB200/GB300/MI355X; MI300X unsupported), base args --trust-remote-code --kv-cache-dtype fp8 --block-size 256, variants (default FP4+FP8, nvfp4, dspark; 960 GB VRAM min), parallelism strategies (TP/TEP/DEP/multi-node/PD), per-hardware overrides, AMD docker image vllm/vllm-openai-rocm:nightly.
- https://docs.sglang.io/llms.txt —  — EXTERNAL URL. Verified: full documentation index including every cookbook recipe; recipe URL pattern https://docs.sglang.io/cookbook/autoregressive/<Provider>/<Model>.md (appending .md returns raw MDX source).
- https://docs.sglang.io/cookbook/autoregressive/intro —  — EXTERNAL URL. Canonical SGLang Cookbook location. 23 vendor families listed (Qwen/Qwen3.6, DeepSeek/DeepSeek-V4, Llama/Llama3.3-70B, GLM/GLM-5.2, Moonshotai/Kimi-K2.7-Code, OpenAI/GPT-OSS, MiniMax, NVIDIA, Mistral, etc.); also a diffusion section and benchmark pages.
- https://github.com/sgl-project/sglang/tree/main/docs_new —  — EXTERNAL URL. Current cookbook SOURCE after migration: cookbook/autoregressive/<Vendor>/<Model>.mdx (Mintlify MDX + docs.json nav). sglang repo LICENSE verified Apache-2.0 ('Copyright 2023-2024 SGLang Team'). Sparse-checkout of docs_new/cookbook is the vendoring target.
- https://github.com/sgl-project/sgl-cookbook —  — EXTERNAL URL. Old cookbook repo — ARCHIVED read-only 2026-06-11, Apache-2.0. Still useful frozen snapshot: plain markdown at docs/autoregressive/<Vendor>/<Model>.md plus structured YAML configs at data/models/src|generated/v<sglang-version>/<model>.yaml (e.g. deepseek.yaml, qwen.yaml) feeding interactive config generators.
- https://raw.githubusercontent.com/sgl-project/sgl-cookbook/main/docs/autoregressive/DeepSeek/DeepSeek-V3_2.md —  — EXTERNAL URL. Verified concrete SGLang recipe example: exact 'sglang serve --model deepseek-ai/DeepSeek-V3.2-Exp --tp 8 --host 0.0.0.0 --port 30000' commands (plus reasoning-parser/tool-call variants), hardware guidance (8x B200 TP=8; 16x H800 TP=16 across 2 nodes; H200/B200/MI355X supported), sections: Introduction, Installation, Deployment, Invocation, Benchmark.

## Details
## 1. SGLang Cookbook

**Canonical source (verified):** https://docs.sglang.io/cookbook/intro — the cookbook migrated into the main SGLang docs. Source files live in the main repo at `github.com/sgl-project/sglang/tree/main/docs_new/cookbook` as **Mintlify MDX** (e.g. `cookbook/autoregressive/Qwen/Qwen3.5.mdx`). The standalone repo `github.com/sgl-project/sgl-cookbook` (previously rendered at cookbook.sglang.io) was **archived read-only on 2026-06-11**; its README points contributors to `sglang/docs_new`. I did not fetch cookbook.sglang.io itself, so whether it still serves or redirects is unverified.

**Structure:** `cookbook/autoregressive/<Vendor>/<Model>` and `cookbook/diffusion/...`, plus benchmark pages. 23 vendor families verified in the autoregressive index, including `DeepSeek/DeepSeek-V4`, `Qwen/Qwen3.6`, `Llama/Llama3.3-70B`, `GLM/GLM-5.2`, `Moonshotai/Kimi-K2.7-Code`, `OpenAI/GPT-OSS`, `MiniMax/MiniMax-M3`, `NVIDIA/Nemotron3-Ultra`, `Mistral/Ministral-3`. The llms.txt index also lists older recipes retained after migration (DeepSeek-R1/V3/V3.1/V3.2, Qwen2.5-VL/Qwen3/Qwen3-Coder/Qwen3.5, Kimi-K2/K2.5/K2.6/Kimi-Linear).

**Per-recipe content (verified on two recipes):**
- Exact serve commands. From the DeepSeek-V3.2 recipe (fetched raw from the archived repo):
  ```
  sglang serve \
    --model deepseek-ai/DeepSeek-V3.2-Exp \
    --tool-call-parser deepseekv31 \
    --reasoning-parser deepseek-v3 \
    --chat-template ./examples/chat_template/tool_chat_template_deepseekv32.jinja \
    --tp 8 --host 0.0.0.0 --port 30000
  ```
  with hardware guidance: 8x B200 (TP=8) or 16x H800 (TP=16, 2 nodes); supported platforms H200/B200/MI355X.
- Docker image tags. From the current Qwen3.5 MDX: `lmsysorg/sglang:latest` (NVIDIA), `lmsysorg/sglang-rocm:v0.5.12.post1-rocm720-mi30x-20260604` (MI300X/MI325X), `...mi35x-...` (MI355X); AMD commands use env prefixes like `SGLANG_USE_AITER=1 ... python3 -m sglang.launch_server`.
- GPU sizing tables: e.g. Qwen3.5-397B-A17B — "H100 (80GB) requires tp=16 (2 nodes)" for BF16 vs "tp=8" for FP8; a table maps each GPU to memory + TP across precisions.
- Benchmarks (TTFT/TPOT/tokens-per-sec at multiple concurrencies) and tuning sections.

**Format caveat (verified):** current pages are MDX — ~90% static text (commands, tables, docker pulls are literal) plus an embedded interactive JSX component (e.g. `<Qwen35Deployment />`, `Playground` with `dockerImages` config objects). Some pages (DeepSeek-V4) are more JSX-heavy, with commands generated dynamically from embedded config objects rather than written as static shell blocks. The archived sgl-cookbook additionally has structured YAML per model at `data/models/src/v<version>/<model>.yaml` (frozen as of June 2026) — the closest thing SGLang has to machine-readable recipes, but no longer maintained there; whether equivalent YAML lives in `docs_new` is **unverified**.

## 2. vLLM recipes

**Canonical source (verified):** https://github.com/vllm-project/recipes, rendered at https://recipes.vllm.ai (144 recipes across 40+ providers, per the site).

**Structure (verified):** two generations coexist:
- Legacy markdown: top-level org dirs (`Qwen/Qwen3.5.md`, `GLM/GLM5.md`, `Google/Gemma4.md`, ...) — being migrated.
- New structured YAML: `models/<hf_org>/<hf_repo>.yaml`, path mirrors HuggingFace so `recipes.vllm.ai/<org>/<repo>` matches `huggingface.co/<org>/<repo>`. Validated/compiled to a JSON API via `node scripts/build-recipes-api.mjs`; CONTRIBUTING says static JSON is exported under `public/` explicitly "for agents/tools to consume" (that quote from a search snippet; the working endpoints below corroborate it).

**Concrete example 1 (YAML, verified raw fetch):** `models/deepseek-ai/DeepSeek-V4-Pro.yaml` — model_id `deepseek-ai/DeepSeek-V4-Pro` (1.6T total / 49B active MoE, 1,048,576-token context); verified-hardware matrix H200/B200/B300/GB200/GB300/MI355X (MI300X/MI325X marked unsupported); base args `--trust-remote-code --kv-cache-dtype fp8 --block-size 256`; variants default(FP4+FP8)/nvfp4/dspark, each min ~960 GB VRAM; parallelism strategies (default `single_node_tep`, plus TP/DEP/multi-node/PD-cluster); per-hardware overrides (Hopper: max-model-len capped at 800k; Blackwell: `--moe-backend deep_gemm_mega_moe`; AMD: `--distributed-executor-backend mp`, docker `vllm/vllm-openai-rocm:nightly`).

**Concrete example 2 (rendered JSON, verified):** `https://recipes.vllm.ai/Qwen/Qwen3-32B.json` — includes `"recommended_command": {"hardware": "h200", "command": "vllm serve Qwen/Qwen3-32B \\\n  --tensor-parallel-size 1 \\\n  --reasoning-parser qwen3"}`, a full `docker_command` using image `vllm/vllm-openai:latest`, `by_hardware` configs (H200/H100/B200/TPU), quantization `variants` (BF16/FP8/AWQ), model metadata (32B params, 40960 ctx, min vLLM version), and a prose `guide`.

## 3. Licenses (both verified from LICENSE files)

- `vllm-project/recipes`: **Apache License 2.0** (raw LICENSE fetched).
- `sgl-project/sglang` (hosts docs_new/cookbook): **Apache License 2.0**, "Copyright 2023-2024 SGLang Team" (raw LICENSE fetched). The archived `sgl-cookbook` repo is also Apache-2.0 (per its repo page).

Implication: runtime fetching, caching, vendoring, and redistribution of recipe content by a dstack-embedded agent are all permitted; if vendoring, retain the Apache-2.0 license text and attribution notices. (Note: the licenses cover the recipe text/config, not the model weights they describe.)

## 4. Runtime WebFetch vs clone/vendor

**vLLM — fetch at runtime, it's designed for it:**
- Index: `GET https://recipes.vllm.ai/models.json` (verified; ~500 entries incl. quantized variants; fields hf_id/title/provider/url/json/derived_from).
- Per model: `GET https://recipes.vllm.ai/<hf_org>/<hf_repo>.json` (verified) — already contains the exact serve command per hardware; no MD parsing needed.
- Fallback/stable raw: `https://raw.githubusercontent.com/vllm-project/recipes/main/models/<hf_org>/<hf_repo>.yaml` (verified working).
- Churn risk: legacy `*/<Model>.md` paths are mid-migration — don't build against those.

**SGLang — fetchable but messier; vendoring is safer:**
- Discoverable at runtime via `https://docs.sglang.io/llms.txt` (verified index) and per-page raw source by appending `.md` (verified: returns MDX source, not clean markdown).
- Risk: content is MDX with JSX components (some recipes like DeepSeek-V4 keep docker images/args inside JSX config objects, not shell blocks), and the cookbook already changed homes once within a month (cookbook.sglang.io → docs.sglang.io), so URL churn risk is real.
- Vendoring option: sparse-checkout of `sglang/docs_new/cookbook` (current, MDX) or the frozen archived `sgl-cookbook` (plain md + structured `data/models/src/*.yaml`, but stale post-2026-06-11).

## 5. Machine-readable indexes

- **vLLM:** `recipes.vllm.ai/models.json` + per-model `/<org>/<model>.json` (both verified). No llms.txt — `https://recipes.vllm.ai/llms.txt` returns **404** (verified).
- **SGLang:** `https://docs.sglang.io/llms.txt` (verified; full doc/cookbook index with .md URLs — Mintlify-style). No JSON recipe API found for SGLang; the archived repo's `data/models/src|generated/v*/{model}.yaml` config-generator data is the nearest equivalent (frozen). Whether docs.sglang.io exposes llms-full.txt or an equivalent JSON is **unverified** (not checked).

## Unverified items (explicit)
- Current behavior of cookbook.sglang.io (redirect vs stale mirror) — not fetched.
- Whether every docs.sglang.io page reliably serves source via the `.md` suffix (verified only for DeepSeek-V4.md).
- The `public/` static-JSON claim in vLLM CONTRIBUTING.md was seen only in a search snippet (endpoints themselves verified live).
- Post-knowledge-cutoff model names (DeepSeek-V4, Qwen3.5/3.6, GLM-5.2, Kimi-K2.7-Code, etc.) are reported exactly as returned by the fetched pages.

## Gotchas
1) The "SGLang Cookbook" GitHub repo (sgl-project/sgl-cookbook) is ARCHIVED (read-only since 2026-06-11) — do not plan around it as the live source; the live source is sgl-project/sglang:docs_new/cookbook and the live site is docs.sglang.io/cookbook (NOT cookbook.sglang.io). 2) SGLang recipe pages are MDX, not plain markdown: appending .md to a docs.sglang.io URL returns raw MDX where some recipes (e.g. DeepSeek-V4) embed docker images and serve-arg matrices inside JSX Playground/ConfigGenerator components rather than static shell blocks — a naive markdown-reading agent will miss or misparse those; older/most recipes (e.g. Qwen3.5) are ~90% static and fine. 3) SGLang cookbook URLs churned once already (repo + domain moved in June 2026), so hardcoded deep links are fragile; resolve via docs.sglang.io/llms.txt at runtime. 4) vLLM recipes repo is mid-migration from per-org markdown to models/<hf_org>/<hf_repo>.yaml — build against recipes.vllm.ai/models.json + per-model JSON (or raw YAML on GitHub), never the legacy .md paths. 5) recipes.vllm.ai has NO llms.txt (404) — its discovery entry point is /models.json; conversely SGLang has llms.txt but NO JSON API. An agent needs two different consumption strategies. 6) Apache-2.0 on both covers the recipe text only, not the model weights the recipes deploy; vendored copies must retain LICENSE/attribution. 7) vLLM's models.json includes ~500 entries but many are quantized variants linked via derived_from — dedupe on that field when presenting model choices.
