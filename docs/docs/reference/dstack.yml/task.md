# `task`

The `task` configuration type allows running [tasks](../../concepts/tasks.md).

## Root reference

#SCHEMA# dstack._internal.core.models.configurations.TaskConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true

### `retry`

#SCHEMA# dstack._internal.core.models.profiles.ProfileRetry
    overrides:
      show_root_heading: false
      type:
        required: true

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
