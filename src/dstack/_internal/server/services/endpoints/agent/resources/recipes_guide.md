# Recipe and Hardware Grounding

Before choosing a deployment, gather enough evidence to explain why the service command and hardware should work.

Primary sources to prefer:

- vLLM docs and recipes: https://docs.vllm.ai/ and https://recipes.vllm.ai/models.json
- SGLang docs and cookbook: https://docs.sglang.ai/
- Hugging Face model cards and framework notes, for example https://huggingface.co/docs/transformers/model_doc/qwen3 and https://huggingface.co/Qwen/Qwen3-0.6B
- dstack documentation and local CLI help.

Supporting sources for advanced direction, not v1 requirements:

- https://www.wafer.ai/blog/glm52-amd
- https://www.lmsys.org/blog/2026-07-02-agent-assisted-sglang-development/
- https://github.com/dstackai/dstack/pull/3856

Recipe selection rubric:

- Prefer an official framework recipe for the exact model. If none exists, use the model family recipe plus the model card.
- Check whether the model needs `trust_remote_code`, special tokenizer/chat template handling, quantization, tensor parallelism, or specific framework versions.
- Estimate VRAM, GPU count, disk, and any CPU/memory needs before looking at offers. For a tiny model, avoid overbuying unless the cheaper path is unstable. For larger models, do not guess; use model size, precision, quantization, KV-cache, and tensor-parallel evidence.
- Treat concrete offers as availability evidence, not as requirements. A selected offer may fail or dstack may provision a different matching offer; final hardware evidence must come from the verified run.
- When evidence is uncertain, use a bounded experiment instead of guessing.
- Record recipe/source URLs in the final report so a learned preset has provenance.
