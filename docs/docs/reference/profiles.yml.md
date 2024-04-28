# profiles.yml

Instead of configuring run options as [`dstack run`](cli/index.md#dstack-run) arguments 
or `.dstack.yml` parameters, you can defines those options in `profiles.yml`
and reuse them across different run configurations.
`dstack` supports repository-level profiles defined in `$REPO_ROOT/.dstack/profiles.yml`
and global profiles defined in `~/.dstack/profiles.yml`.

Profiles parameters are resolved with the following priority:

1. `dstack run` arguments
2. `.dstack.yml` parameters
3. Repository-level profiles from `$REPO_ROOT/.dstack/profiles.yml`
4. Global profiles from `~/.dstack/profiles.yml`

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
