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

#### `ssh_config.proxy_jump` { #ssh_config-proxy_jump data-toc-label="proxy_jump" }

#SCHEMA# dstack._internal.core.models.fleets.SSHProxyParams
    overrides:
      show_root_heading: false
      item_id_prefix: proxy_jump-

#### `ssh_config.hosts[n]` { #ssh_config-hosts data-toc-label="hosts" }

#SCHEMA# dstack._internal.core.models.fleets.SSHHostParams
    overrides:
      show_root_heading: false

##### `ssh_config.hosts[n].proxy_jump` { #proxy_jump data-toc-label="hosts[n].proxy_jump" }

#SCHEMA# dstack._internal.core.models.fleets.SSHProxyParams
    overrides:
      show_root_heading: false
      item_id_prefix: hosts-proxy_jump-

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

### `retry`

#SCHEMA# dstack._internal.core.models.profiles.ProfileRetry
    overrides:
      show_root_heading: false
