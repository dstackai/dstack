# `service`

The `service` configuration type allows running [services](../../concepts/services.md).

## Root reference

#SCHEMA# dstack._internal.core.models.configurations.ServiceConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true

### `model` { data-toc-label="model" }

=== "OpenAI"

    #SCHEMA# dstack.api.OpenAIChatModel
        overrides:
          show_root_heading: false
          type:
            required: true


### `scaling`

#SCHEMA# dstack._internal.core.models.configurations.ScalingSpec
    overrides:
      show_root_heading: false
      type:
        required: true

### `rate_limits`

#### `rate_limits[n]`

#SCHEMA# dstack._internal.core.models.configurations.RateLimit
    overrides:
      show_root_heading: false
      type:
        required: true

##### `rate_limits[n].key` { data-toc-label="key" }

=== "IP address"

    Partition requests by client IP address.

    #SCHEMA# dstack._internal.core.models.configurations.IPAddressPartitioningKey
        overrides:
          show_root_heading: false
          type:
            required: true

=== "Header"

    Partition requests by the value of a header.

    #SCHEMA# dstack._internal.core.models.configurations.HeaderPartitioningKey
        overrides:
          show_root_heading: false
          type:
            required: true

### `probes`

#### `probes[n]`

#SCHEMA# dstack._internal.core.models.configurations.ProbeConfig
    overrides:
      show_root_heading: false
      type:
        required: true

##### `probes[n].headers`

###### `probes[n].headers[m]`

#SCHEMA# dstack._internal.core.models.configurations.HTTPHeaderSpec
    overrides:
      show_root_heading: false
      type:
        required: true


### `replicas`

#### `replicas[n]`

#SCHEMA# dstack._internal.core.models.configurations.ReplicaGroup
    overrides:
      show_root_heading: false
      type:
        required: true

### `retry`

#SCHEMA# dstack._internal.core.models.profiles.ProfileRetry
    overrides:
      show_root_heading: false

### `utilization_policy`

#SCHEMA# dstack._internal.core.models.profiles.UtilizationPolicy
    overrides:
      show_root_heading: false
      type:
        required: true

### `schedule`

#SCHEMA# dstack._internal.core.models.profiles.Schedule
    overrides:
      show_root_heading: false
      type:
        required: true

### `resources`

#SCHEMA# dstack._internal.core.models.resources.ResourcesSpec
    overrides:
      show_root_heading: false
      type:
        required: true
      item_id_prefix: resources-

#### `resources.cpu` { #resources-cpu data-toc-label="cpu" }

#SCHEMA# dstack._internal.core.models.resources.CPUSpec
    overrides:
      show_root_heading: false
      type:
        required: true

#### `resources.gpu` { #resources-gpu data-toc-label="gpu" }

#SCHEMA# dstack._internal.core.models.resources.GPUSpec
    overrides:
      show_root_heading: false
      type:
        required: true

#### `resources.disk` { #resources-disk data-toc-label="disk" }

#SCHEMA# dstack._internal.core.models.resources.DiskSpec
    overrides:
      show_root_heading: false
      type:
        required: true

### `registry_auth`

#SCHEMA# dstack._internal.core.models.configurations.RegistryAuth
    overrides:
      show_root_heading: false
      type:
        required: true

### `volumes[n]` { #_volumes data-toc-label="volumes" }

=== "Network volumes"

    #SCHEMA# dstack._internal.core.models.volumes.VolumeMountPoint
        overrides:
          show_root_heading: false
          type:
            required: true

=== "Instance volumes"

    #SCHEMA# dstack._internal.core.models.volumes.InstanceMountPoint
        overrides:
          show_root_heading: false
          type:
            required: true

??? info "Short syntax"

    The short syntax for volumes is a colon-separated string in the form of `source:destination`

    * `volume-name:/container/path` for network volumes
    * `/instance/path:/container/path` for instance volumes

### `repos[n]` { #_repos data-toc-label="repos" }

> Currently, a maximum of one repo is supported.

> Either `local_path` or `url` must be specified.

#SCHEMA# dstack._internal.core.models.configurations.RepoSpec
    overrides:
      show_root_heading: false
      type:
        required: true

??? info "`if_exists` action"

    If the `path` already exists and is a non-empty directory, by default the run is terminated with an error.
    This can be changed with the `if_exists` option:

    * `error` – do not try to check out, terminate the run with an error (the default action since `0.20.0`)
    * `skip` – do not try to check out, skip the repo (the only action available before `0.20.0`)

    Note, if the `path` exists and is _not_ a directory (e.g., a regular file), this is always an error that
    cannot be ignored with the `skip` action.

??? info "Short syntax"

    The short syntax for repos is a colon-separated string in the form of `local_path_or_url:path`.

    * `.:/repo`
    * `..:repo`
    * `~/repos/demo:~/repo`
    * `https://github.com/org/repo:~/data/repo`
    * `git@github.com:org/repo.git:data/repo`

### `files[n]` { #_files data-toc-label="files" }

#SCHEMA# dstack._internal.core.models.files.FilePathMapping
    overrides:
      show_root_heading: false
      type:
        required: true

??? info "Short syntax"

    The short syntax for files is a colon-separated string in the form of `local_path[:path]` where
    `path` is optional and can be omitted if it's equal to `local_path`.

    * `~/.bashrc`, same as `~/.bashrc:~/.bashrc`
    * `/opt/myorg`, same as `/opt/myorg/` and `/opt/myorg:/opt/myorg`
    * `libs/patched_libibverbs.so.1:/lib/x86_64-linux-gnu/libibverbs.so.1`
