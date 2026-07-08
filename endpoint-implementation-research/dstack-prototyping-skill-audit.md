# dstack-prototyping Skill Audit

Date: 2026-07-07

Purpose: rebuild `skills/dstack-prototyping/SKILL.md` from validated, high-value
instructions only. This file is a working audit for this branch, not user docs.

## Skill Bar

A sentence stays in the skill only if it passes at least one test:

- It prevents a failure we already observed in endpoint e2e.
- It is a dstack fact verified by docs, CLI help, or source code.
- It is a fragile endpoint-agent contract the model must see during execution.
- It tells the agent how to choose between task, dev environment, service, fleet,
  backend, image, resources, cache, or verification.

A sentence is removed or moved out if it is:

- generic project-management advice;
- a competitor/product idea that does not change the next deployment decision;
- a future optimization topic unrelated to getting a verified endpoint;
- a claim about backend behavior not supported by docs, code, run evidence, or
  harness-provided facts;
- a restatement of `/dstack` CLI syntax unless the endpoint harness depends on
  the distinction.

## Validated Facts

| Fact | Source | Decision |
| --- | --- | --- |
| dstack has VM-based and container-based backends. | `mkdocs/docs/concepts/backends.md` | Keep. Critical for experiment strategy. |
| VM-based backends give dstack native control over provisioning. | `mkdocs/docs/concepts/backends.md` | Keep, but avoid saying every VM backend is always better. |
| Container-based backends delegate provisioning to the provider or Kubernetes. | `mkdocs/docs/concepts/backends.md` | Keep, but do not overgeneralize to no cache/no SSH without evidence. |
| SSH fleets exist without backend configuration and use user/admin-managed hosts. | `mkdocs/docs/concepts/backends.md`, `mkdocs/docs/concepts/fleets.md` | Keep. Strong signal for interactive prototyping. |
| Fleets must exist before runs. | `mkdocs/docs/concepts/fleets.md`, task/dev/service docs | Keep. Endpoint agent must not create fleets. |
| Backend fleets with `nodes` starting at `0` create only a template; instances are provisioned by runs. | `mkdocs/docs/concepts/fleets.md` | Keep for reasoning about cold starts. |
| Pre-provisioning is supported only for VM-based backends. | `mkdocs/docs/concepts/fleets.md` | Keep. Important distinction from container backends. |
| Fleet `idle_duration` keeps idle backend-fleet instances around for reuse. | `mkdocs/docs/concepts/fleets.md`, snippets | Keep. Explains warm-instance strategy. |
| `dstack offer` ignores fleet configs by default. `--fleet` restricts offers to selected fleets. | `mkdocs/docs/reference/cli/dstack/offer.md` | Keep. Prevents global-offer mistakes. |
| `dstack offer --group-by gpu,backend` is documented and `gpu` must be included. | `mkdocs/docs/reference/cli/dstack/offer.md`, CLI help | Keep. Useful for multi-backend fleets. |
| Offer output is hardware/capacity/price, not proof of backend implementation class. | Inference from offer docs + observed failure | Keep as a guardrail. Label as interpretation, not doc quote. |
| Dev environments are accessible via IDE or SSH. | `mkdocs/docs/concepts/dev-environments.md` | Keep. Useful for interactive probe choice. |
| Tasks run arbitrary commands and can be single-node or distributed. | `mkdocs/docs/concepts/tasks.md` | Keep only the part needed for probes. |
| Services are final endpoint artifacts and can expose OpenAI-compatible model URLs when `model` is set. | `mkdocs/docs/concepts/services.md`, `/dstack` skill | Keep. Final proof depends on it. |
| Resource ranges are supported for CPU/memory/GPU/disk. | task/dev docs, offer reference, CLI help | Keep briefly. |
| GPU spec can include vendor/model/memory/count. | offer reference, dev docs, CLI help | Keep for vendor-aware recipes. |
| Instance volumes can be optional; optional volumes run even if the selected backend cannot mount them. | `mkdocs/docs/concepts/volumes.md` | Keep. Useful for cache mounts without over-constraining placement. |
| Instance volumes are not supported on RunPod and Vast.ai in docs. | `mkdocs/docs/concepts/volumes.md` | Keep carefully; do not extrapolate to all persistence. |
| Local code exposes backend feature lists for create-instance, instance-volumes, privileged, multinode. | `src/dstack/_internal/core/backends/features.py` | Keep if harness injects them. |
| `ComputeWithCreateInstanceSupport` is documented in code as fleet instance creation without running a job; typically VMs implement it and containers do not. | `src/dstack/_internal/core/backends/base/compute.py` | Keep as implementation signal, not public UX. |
| JarvisLabs supports create-instance, privileged, and instance-volumes in this build. | `src/dstack/_internal/core/backends/jarvislabs/compute.py` | Keep in harness hints, not hardcoded in the generic skill. |
| RunPod supports group provisioning, multinode, and network volumes but not create-instance or instance-volumes in this build. | `src/dstack/_internal/core/backends/runpod/compute.py`, features list | Keep in harness hints, not hardcoded in the generic skill. |
| `python` and `image` are mutually exclusive in run configs. | `/dstack` skill | Do not duplicate unless endpoint failures show agents violate it. |

## Observed Endpoint-Agent Failures To Prevent

| Failure | Skill/prompt rule |
| --- | --- |
| Agent called JarvisLabs container-style because RunPod rows appeared first in offers. | Classify allowed backends from docs/code/harness facts before relying on offers; offers are not backend-class proof. |
| Agent chose RunPod by omission because service/task YAML did not pin `backends`. | If YAML omits `backends`, admit scheduler may choose any matching backend allowed by constraints. |
| Agent packed a whole probe into task `commands` instead of making an interactive target. | Probe task should stay alive when attach/SSH is available; run checks through attach/SSH. |
| Agent promoted based on shallow host evidence. | `nvidia-smi` alone is not recipe proof. Probe must test the intended image/framework/model/server slice. |
| Agent used `latest` image and hit driver/runtime mismatch. | Final service image should be pinned or justified by source/probe. |
| Agent resubmitted services and paid cold-start cost repeatedly. | Prefer task/dev probes and reusable/inspectable backends when they can reduce total iteration. |
| Endpoint logs had vague categories and little reasoning. | Progress must explain decisions and evidence in natural language. |
| Service reached healthy before endpoint became running. | Final service must still be verified by agent and reported; endpoint success is not service status alone. |

## Keep In Skill

- Load `/dstack` first and do not duplicate CLI syntax.
- Define success as verified final service model request.
- Require the agent to decide the proof request, model facts, framework, resource envelope,
  constraints, and first experiment before paid runs, without forcing a markdown note.
- Require existing fleets; endpoint agents do not create/edit fleets.
- Use fleet-filtered offers, not global offers, when endpoint capacity is fleet-bounded.
- Compare multi-backend fleets with the intended resource envelope.
- Classify backend choice from docs/code/harness/run evidence, not truncated offers.
- Prefer inspectable/reusable placements when viable, but allow container paths with a reason.
- Derive minimum resources separately from selected offers and validation hardware.
- Use vendor-aware GPU resources after the recipe or placement is vendor-specific.
- Verify driver/runtime when it affects image/framework choice.
- Prefer task/dev probe before final service for new recipes on unverified paths.
- Make probes interactive when attach/SSH is available.
- Probe the intended serving stack, not just GPU visibility.
- Pin final images or justify them from source/probe.
- Use optional instance cache mounts when useful and supported; do not assume persistence.
- Use run JSON/events/logs/attached shell for different evidence types.
- Classify failures before changing YAML.
- Promote only a clean service and verify the model URL with a real request.
- Keep endpoint progress human-readable and structured endpoint files parseable.

## Remove From Skill

- Long competitor-link explanations. Keep references in research/test-plan docs; the skill should not push v1 agents toward benchmarking or kernel work.
- Generic "do not chase local optimum" phrasing. Replace with concrete decision gates.
- Full lists of every possible failure unless they guide the immediate next edit.
- Detailed final report schema duplication that belongs in the endpoint prompt.
- Broad claims such as "VM is better" without constraints.
- Any backend-specific fact that can be injected by the harness for the actual project.

## Rebuild Shape

The rebuilt `SKILL.md` should be short enough for the agent to actually follow:

1. Scope and success gate.
2. Pre-run decisions.
3. Fleet/backend choice.
4. Hardware/resources.
5. Experiment selection.
6. Probe quality.
7. Images/cache.
8. Evidence/failure routing.
9. Promotion/final verification.
10. Endpoint progress and structured files.
