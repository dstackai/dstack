---
title: What is dstack?
description: Introduction to dstack and how it works
---

# What is dstack?

`dstack` is a unified control plane for GPU provisioning and orchestration that works with any GPU cloud, Kubernetes, or on-prem clusters. 

It streamlines development, training, and inference, and is compatible with any hardware, open-source tools, and frameworks.

!!! info "Accelerators"
    `dstack` supports `NVIDIA`, `AMD`, `TPU`, and `Tenstorrent` accelerators out of the box.

## How does it work?

<!-- Architecture diagram — ported from the new landing's <ArchitectureDiagram> component.
     Styles live in mkdocs/assets/stylesheets/cloudscape-docs.css (.arch-*). If the landing
     diagram changes (website/src/components/ArchitectureDiagram.tsx), update this markup + CSS. -->
<div class="arch-diagram-wrap"><div class="arch-diagram" role="img" aria-label="dstack architecture: an orchestration layer between AI frameworks, data, and models on top, and GPU clouds, Kubernetes, on-prem clusters, and hardware below."><div class="arch-row"><div class="arch-cell"><svg class="arch-dash" aria-hidden="true"><rect/></svg><span class="arch-cell__label">Any framework</span><span class="arch-logos"><span class="arch-logo arch-logo--pytorch" role="img" aria-label="PyTorch"></span><span class="arch-logo arch-logo--vllm" role="img" aria-label="vLLM"></span><span class="arch-logo arch-logo--sglang" role="img" aria-label="SGLang"></span><span class="arch-logo arch-logo--meta" role="img" aria-label="Meta"></span><span class="arch-logo arch-logo--huggingface" role="img" aria-label="Hugging Face"></span></span></div><div class="arch-cell arch-cell--center"><svg class="arch-dash" aria-hidden="true"><rect/></svg><span class="arch-cell__label">Your data</span></div><div class="arch-cell arch-cell--center"><svg class="arch-dash" aria-hidden="true"><rect/></svg><span class="arch-cell__label">Any models</span></div></div><div class="arch-orchestration"><div class="arch-orchestration__title">The AI-native orchestration stack</div><div class="arch-orchestration__cells"><div class="arch-subcell"><svg class="arch-dash" aria-hidden="true"><rect/></svg>Fleets</div><div class="arch-subcell"><svg class="arch-dash" aria-hidden="true"><rect/></svg>Dev environments</div><div class="arch-subcell"><svg class="arch-dash" aria-hidden="true"><rect/></svg>Tasks</div><div class="arch-subcell"><svg class="arch-dash" aria-hidden="true"><rect/></svg>Services</div><div class="arch-subcell"><svg class="arch-dash" aria-hidden="true"><rect/></svg>Volumes</div></div></div><div class="arch-row"><div class="arch-cell arch-cell--gpu"><svg class="arch-dash" aria-hidden="true"><rect/></svg><span class="arch-logos"><span class="arch-logo arch-logo--aws" role="img" aria-label="AWS"></span><span class="arch-logo arch-logo--gcp" role="img" aria-label="Google Cloud"></span><span class="arch-logo arch-logo--lambda" role="img" aria-label="Lambda"></span><span class="arch-logo arch-logo--nebius" role="img" aria-label="Nebius"></span><span class="arch-logo arch-logo--runpod" role="img" aria-label="RunPod"></span></span><span class="arch-cell__label">Any cloud</span></div><div class="arch-cell"><svg class="arch-dash" aria-hidden="true"><rect/></svg><span class="arch-logos"><span class="arch-logo arch-logo--kubernetes" role="img" aria-label="Kubernetes"></span></span><span class="arch-cell__label">Kubernetes</span></div><div class="arch-cell arch-cell--center"><svg class="arch-dash" aria-hidden="true"><rect/></svg><span class="arch-cell__label">On-prem clusters</span></div></div><div class="arch-cell arch-cell--full arch-cell--hw"><svg class="arch-dash" aria-hidden="true"><rect/></svg><span class="arch-cell__label">Any hardware</span><span class="arch-logos"><span class="arch-logo arch-logo--nvidia" role="img" aria-label="NVIDIA"></span><span class="arch-logo arch-logo--amd" role="img" aria-label="AMD"></span><span class="arch-logo arch-logo--tenstorrent" role="img" aria-label="Tenstorrent"></span><span class="arch-logo arch-logo--tpu" role="img" aria-label="Google TPU"></span></span></div></div></div>

### Set up the server

> Before using `dstack`, ensure you've [installed](installation.md) the server, or signed up for [dstack Sky](https://sky.dstack.ai).

### Define configurations

`dstack` supports the following configurations:
   
* [Fleets](concepts/fleets.md) &mdash; for managing cloud and on-prem clusters
* [Dev environments](concepts/dev-environments.md) &mdash; for interactive development using a desktop IDE
* [Tasks](concepts/tasks.md) &mdash; for scheduling jobs, incl. distributed ones (or running web apps)
* [Services](concepts/services.md) &mdash; for deploying models (or web apps)
* [Volumes](concepts/volumes.md) &mdash; for managing network volumes (to persist data)

Configuration can be defined as YAML files within your repo.

### Apply configurations

Apply the configuration either via the `dstack apply` CLI command (or through a programmatic API.)

`dstack` automatically manages infrastructure provisioning and job scheduling, while also handling auto-scaling,
port-forwarding, ingress, and more.

!!! info "Where do I start?"
    1. Proceed to [installation](installation.md)
    2. See [quickstart](quickstart.md)
    3. Browse [examples](/examples)
    4. Join [Discord](https://discord.gg/u8SmfwPpMd)
