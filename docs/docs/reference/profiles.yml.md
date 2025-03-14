# profiles.yml

Sometimes, you may want to reuse the same parameters across different [`.dstack.yml`](dstack.yml.md) configurations.

This can be achieved by defining those parameters in a profile.

Profiles can be defined on the repository level (via the `.dstack/profiles.yml` file in the root directory of the
repository) or on the global level (via the `~/.dstack/profiles.yml` file).

Any profile can be marked as default so that it will be applied automatically for any run. Otherwise, you can refer to a specific profile
via `--profile NAME` in `dstack apply`.

### Example

<div editor-title=".dstack/profiles.yml"> 

```yaml
profiles:
  - name: my-profile

    # The spot pololicy can be "spot", "on-demand", or "auto"
    spot_policy: auto

    # Limit the maximum price of the instance per hour
    max_price: 1.5

    # Stop any run if it runs longer that this duration
    max_duration: 1d

    # Use only these backends
    backends: [azure, lambda]

    # If set to true, this profile will be applied automatically
    default: true
```

</div>

The profile configuration supports many properties. See below.

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
