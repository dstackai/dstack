---
name: dstack-presets
description: |
  Create and manage dstack presets: a toolkit that streamlines model inference optimization with agents, and a portable preset format. Use together with the dstack skill, and only when the user explicitly asks to create a preset or manage existing presets, not for deploying or serving a model.
---

# dstack Presets

Use `/dstack` for CLI commands, YAML fields, apply behavior, fleets, and other
dstack syntax. This skill covers creating and managing presets.

## Overview

Presets offer two things: a toolkit that streamlines model inference optimization using agents, and a portable format that deploys the final preset to any cloud, Kubernetes cluster, or bare-metal fleet. A preset holds the serving configuration that produced the result, the benchmark it reached, and the exact hardware it was verified on.

Presets are used for three kinds of work: finding an optimized baseline, optimizing through patching source code, and supporting new hardware.

**When to use this skill:**
- The user explicitly asks to create a preset, or to optimize model inference via a preset
- Managing already created presets: watching sessions, listing, exporting, and deleting them via `dstack preset` commands

**When NOT to use this skill:**
- Deploying or serving a model: use a service instead (see the `dstack` skill)

## How to use presets

Follow the [presets documentation](https://dstack.ai/docs/concepts/presets.md).

[Configuration reference](https://dstack.ai/docs/reference/dstack.yml/preset.md) | [CLI reference](https://dstack.ai/docs/reference/cli/dstack/preset.md)
