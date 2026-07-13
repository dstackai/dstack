# `endpoint`

The `endpoint` configuration type describes a model request and the constraints
used to create or apply an [endpoint preset](../../concepts/endpoints.md).

## Root reference

#SCHEMA# dstack._internal.core.models.endpoints.EndpointConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true

### `model`

=== "Base model"

    Allows the creation agent to select a compatible model variant.

    #SCHEMA# dstack._internal.core.models.endpoints.EndpointModelBase
        overrides:
          show_root_heading: false

=== "Exact model"

    Requires an exact model repo or path and optionally sets another
    client-facing model name.

    #SCHEMA# dstack._internal.core.models.endpoints.EndpointModelRepo
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
