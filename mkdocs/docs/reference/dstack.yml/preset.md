# `preset`

The `preset` configuration type describes a model request and the constraints
used to create or apply a [preset](../../concepts/presets.md).

## Root reference

#SCHEMA# dstack._internal.cli.models.configurations.PresetConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true

### `model`

=== "Base model"

    Allows the creation agent to select a compatible model variant.

    #SCHEMA# dstack._internal.cli.models.configurations.PresetModelBase
        overrides:
          show_root_heading: false

=== "Exact model"

    Requires an exact model repo or path and optionally sets another
    client-facing model name.

    #SCHEMA# dstack._internal.cli.models.configurations.PresetModelRepo
        overrides:
          show_root_heading: false

### `prompt`

Custom agent instructions. Set to an inline string, or to a file:

#SCHEMA# dstack._internal.cli.models.configurations.PresetPromptFile
    overrides:
      show_root_heading: false

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

### `instances[n]` { #_instances data-toc-label="instances" }

When `instances` is set, the run is placed only on matching existing fleet instances.

=== "By name"

    #SCHEMA# dstack._internal.core.models.profiles.InstanceNameSelector
        overrides:
          show_root_heading: false
          type:
            required: true

=== "By hostname"

    #SCHEMA# dstack._internal.core.models.profiles.InstanceHostnameSelector
        overrides:
          show_root_heading: false
          type:
            required: true

=== "By fleet and instance number"

    #SCHEMA# dstack._internal.core.models.profiles.FleetInstanceSelector
        overrides:
          show_root_heading: false
          type:
            required: true

??? info "Short syntax"

    The short syntax for instances is an instance name string.

    * `my-fleet-1`, same as `{name: my-fleet-1}`

### `backend_options`

Backend-specific options that only take effect for offers of the respective backend.

#### `backend_options[n][type=vastai]` { #backend_options-vastai data-toc-label="vastai" }

#SCHEMA# dstack._internal.core.backends.vastai.profile_options.VastAIProfileOptions
    overrides:
      show_root_heading: false
      type:
        required: true
