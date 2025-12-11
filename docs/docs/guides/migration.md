# Migration guide

<!-- TODO: Add general sections on how to migrate to newer releases and how major and minor versions compatibility  and deprecation policy is handled -->

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
