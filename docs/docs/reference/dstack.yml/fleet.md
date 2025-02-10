# `fleet`

The `fleet` configuration type allows creating and updating fleets.

## Root reference

#SCHEMA# dstack._internal.core.models.fleets.FleetConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true

### `ssh_config` { data-toc-label="ssh_config" }

#SCHEMA# dstack._internal.core.models.fleets.SSHParams
    overrides:
      show_root_heading: false
      item_id_prefix: ssh_config-

#### `ssh_config.hosts[n]` { #ssh_config-hosts data-toc-label="hosts" }

#SCHEMA# dstack._internal.core.models.fleets.SSHHostParams
    overrides:
      show_root_heading: false

### `resources`

#SCHEMA# dstack._internal.core.models.resources.ResourcesSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true
      item_id_prefix: resources-

#### `resouces.gpu` { #resources-gpu data-toc-label="gpu" } 

#SCHEMA# dstack._internal.core.models.resources.GPUSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true

#### `resouces.disk` { #resources-disk data-toc-label="disk" }

#SCHEMA# dstack._internal.core.models.resources.DiskSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true

### `retry`

#SCHEMA# dstack._internal.core.models.profiles.ProfileRetry
    overrides:
      show_root_heading: false
