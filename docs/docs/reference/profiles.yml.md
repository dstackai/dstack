# profiles.yml

Instead of configuring run options through[`dstack run`](cli/index.md#dstack-run), 
you can do so via `.dstack/profiles.yml` in the root folder of the project. 

## Example

<div editor-title=".dstack/profiles.yml"> 

```yaml
profiles:
  - name: large

    spot_policy: auto # (Optional) The spot policy. Supports `spot`, `on-demand, and `auto`.

    max_price: 1.5 # (Optional) The maximum price per instance per hour
    
    max_duration: 1d # (Optional) The maximum duration of the run.

    retry:
      retry-duration: 3h # (Optional) To wait for capacity
    
    backends: [azure, lambda]  # (Optional) Use only listed backends 

    default: true # (Optional) Activate the profile by default
```

</div>

You can mark any profile as default or pass its name via `--profile` to `dstack run`.

### Root reference

#SCHEMA# dstack._internal.core.models.profiles.Profile
    overrides:
      show_root_heading: false
      max_price:
        type: 'Optional[float]'

### `retry_policy`

#SCHEMA# dstack._internal.core.models.profiles.ProfileRetryPolicy
    overrides:
      show_root_heading: false
