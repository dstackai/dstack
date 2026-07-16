# `endpoint`

The `endpoint` configuration type describes a model request and the constraints
used to create or apply an [endpoint preset](../../concepts/endpoints.md).

## Root reference

#SCHEMA# dstack._internal.cli.models.endpoints.EndpointConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true

### `model`

=== "Base model"

    Allows the creation agent to select a compatible model variant.

    #SCHEMA# dstack._internal.cli.models.endpoints.EndpointModelBase
        overrides:
          show_root_heading: false

=== "Exact model"

    Requires an exact model repo or path and optionally sets another
    client-facing model name.

    #SCHEMA# dstack._internal.cli.models.endpoints.EndpointModelRepo
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
