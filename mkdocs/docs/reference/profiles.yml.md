# .dstack/profiles.yml

Sometimes, you may want to reuse the same parameters across runs or set your own defaults so you don’t have to repeat them in every run configuration. You can do this by defining a profile, either globally in `~/.dstack/profiles.yml` or locally in `.dstack/profiles.yml`. 

A profile can be set as `default` to apply automatically to any run, or specified with `--profile NAME` in `dstack apply`.

Example:

<div editor-title=".dstack/profiles.yml"> 

```yaml
profiles:
  - name: my-profile
    # If set to true, this profile will be applied automatically
    default: true

    # The spot pololicy can be "spot", "on-demand", or "auto"
    spot_policy: auto
    # Limit the maximum price of the instance per hour
    max_price: 1.5
    # Stop any run if it runs longer that this duration
    max_duration: 1d
    # Use only these backends
    backends: [azure, lambda]
```

</div>

The profile configuration supports most properties that a run configuration supports — see below.

### Root reference

#SCHEMA# dstack._internal.core.models.profiles.Profile
    overrides:
      show_root_heading: false
      max_price:
        type: 'Optional[float]'

### `retry`

#SCHEMA# dstack._internal.core.models.profiles.ProfileRetry
    overrides:
      show_root_heading: false

### `utilization_policy`

#SCHEMA# dstack._internal.core.models.profiles.UtilizationPolicy
    overrides:
      show_root_heading: false
