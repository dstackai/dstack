---
title: Upgrade
description: Upgrading to newer versions of dstack
---

# Upgrade guide

<!-- TODO: Describe the deprecation policy -->

!!! info "Backward compatibility"
    `dstack` follows the `{major}.{minor}.{patch}` versioning scheme. The sections below cover each minor version and list the changes that may require action when upgrading.

    - The server is backward-compatible with CLIs of the same minor version or older.
    - CLIs of a newer minor version are rejected by older servers (e.g., a `0.22.*` CLI with a `0.21.*` server).

!!! info "Rolling upgrades"
    - The server applies database migrations automatically on startup.
    - Rolling upgrades are supported from older versions, including when skipping releases (e.g., `0.21.0` to `0.22.6`).

Exceptions are noted in the sections below.

## 0.22.* { #0_22 }

!!! info "Rolling upgrades"
    Rolling upgrades to `0.22.*` are supported from `0.21.*`. If upgrading from `0.20.*`, scale server replicas down to `1` before upgrading.

### Exports and Events

Support for [exports](../concepts/exports.md) and the global `Events` page has moved from the open-source version to [dstack Sky](https://dstack.ai/products/sky/) and [dstack Factory](https://dstack.ai/products/factory/). The `dstack event` CLI command and the `Events` tabs on resource pages remain available in the open-source version.

### Deprecations

The `DSTACK_ROUTER_INTERNAL_IP` environment variable is deprecated in favor of [`${{ groups[i].replicas[j].IP_ADDRESS }}`](../concepts/services.md#replica-groups).

## 0.21.* { #0_21 }

> CLI versions prior to `0.20.0` must be upgraded along with the server.

### Pydantic v2

`dstack` has migrated from Pydantic v1 to Pydantic v2. The `dstack` Python API and `dstack` plugins now work with Pydantic v2 models.

> If you use the Python API or have plugins installed, ensure the code works with Pydantic v2 models before upgrading.

If you call the `dstack` HTTP API directly, note that UTC datetimes are now serialized with a `Z` suffix instead of `+00:00`.

### Gateway routers

The top-level `router` property of gateway and run configurations, deprecated in `0.20.17` in favor of [replica-based routers](../concepts/services.md#router), has been removed. Configurations that use it are no longer accepted, and the behavior of gateways and services created with it before the upgrade is undefined.

> Terminate services and gateways that use the top-level `router` property before upgrading, then recreate them using replica-based routers.

### Presets

[Preset](../concepts/presets.md) configuration properties have changed: `max_trials` is now `trials`, and `context_length` is now `min_context_length`. The `max_ttft`, `min_context_length`, and `concurrency` properties no longer have defaults and must be specified. Presets are an experimental feature, so no aliases were kept - existing configurations fail with `extra fields not permitted`.

> Update preset configurations to the new property names before upgrading.

### Deprecated feature removal

The following deprecated API endpoints have been removed in **0.21**:

- `/api/project/{project_name}/runs/submit`
- `/api/project/{project_name}/fleets/create`

Use the corresponding replacements:

- `/api/project/{project_name}/runs/apply`
- `/api/project/{project_name}/fleets/apply`

### Deprecations

The following API response fields are no longer populated by the server and will be removed in a future release:

- `Resources.description`
- `Gateway.backend`
- `Gateway.region`

> For gateways, use `Gateway.configuration.backend` and `Gateway.configuration.region` instead.

> For more details on the changes, see the [release notes](https://github.com/dstackai/dstack/releases).

## 0.20.* { #0_20 }

### Fleets

* Prior to `0.20`, `dstack` automatically provisioned a fleet if one did not exist at run time.  
  Beginning with `0.20`, `dstack` will only use existing fleets.

> Create fleets before submitting runs. To enable on-demand instance provisioning, configure `nodes` as a range in the [backend fleet](../concepts/fleets.md#backend-fleets) configuration.  

### Working directory

- Previously, when `working_dir` was not specified, `dstack` defaulted to `/workflow`. As of `0.20`, `dstack` uses the working directory defined in the Docker image. If the image does not define a working directory, `dstack` falls back to `/`.
- The default image introduced in `0.20` uses `/dstack/run` as its default working directory.

> To override the directory defined in the Docker image, specify [`working_dir`](../concepts/dev-environments.md#working-directory) explicitly.

### Repo directory

- Previously, if no [repo directory](../concepts/dev-environments.md#repos) was specified, `dstack` cloned the repository into `/workflow`. With `0.20`, the working directory becomes the default repo directory.
- In earlier versions, cloning was skipped if the repo directory was non-empty. Starting with `0.20`, this results in a `runner error` unless `if_exists` is set to `skip` in the repo configuration.

> Ensure repo directories are empty, or explicitly set `if_exists` to `skip`.

### Deprecated feature removal

The following deprecated commands have been removed in **0.20**:

- `dstack config`
- `dstack stats`
- `dstack gateway create`

Use the corresponding replacements:

- `dstack project`
- `dstack metrics`
- `dstack apply`

> For more details on the changes, see the [release notes](https://github.com/dstackai/dstack/releases).
