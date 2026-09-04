---
title: Upgrade
description: Upgrading to newer versions of dstack
---

# Upgrade guide

<!-- TODO: Add general sections on how to migrate to newer releases and how major and minor versions compatibility  and deprecation policy is handled -->

## 0.21.* { #0_21 }

### CLI compatibility

- CLI versions `0.20.*` and later remain backward compatible with the `0.21.*` `dstack` server.
- CLI versions `0.21.*` are not compatible with server versions prior to `0.21.*`.

> Upgrade the server before upgrading the CLI, or upgrade both at the same time. CLI versions prior to `0.20.0` must be upgraded along with the server.

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

The following API response fields are no longer populated by the server and will be removed in **0.22**:

- `Resources.description`
- `Gateway.backend`
- `Gateway.region`

> For gateways, use `Gateway.configuration.backend` and `Gateway.configuration.region` instead.

> For more details on the changes, see the [release notes](https://github.com/dstackai/dstack/releases).

## 0.20.* { #0_20 }

### CLI compatibility

- CLI versions `0.19.*` and earlier remain backward compatible with the `0.20.*` `dstack` server.
- CLI versions `0.20.` are not compatible with server versions prior to `0.20.*`.

> Do not upgrade the CLI to `0.20.*` until the server has been upgraded.

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
