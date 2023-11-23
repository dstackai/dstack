# profiles.yml

Instead of configuring resources and other run options through[`dstack run`](cli/index.md#dstack-run), 
you can do so via `.dstack/profiles.yml` in the root folder of the project. 

## Example

<div editor-title=".dstack/profiles.yml"> 

```yaml
profiles:
  - name: large

    resources:
      memory: 24GB  # (Optional) The minimum amount of RAM memory
      gpu:
        name: A100 # (Optional) The name of the GPU
        memory: 40GB # (Optional) The minimum amount of GPU memory 
      shm_size: 8GB # (Optional) The size of shared memory
    
    spot_policy: auto # (Optional) The spot policy. Supports `spot`, `on-demand, and `auto`.

    max_price: 1.5 # (Optional) The maximum price per instance per hour
    
    max_duration: 1d # (Optional) The maximum duration of the run.

    retry:
      retry-limit: 3h # (Optional) To wait for capacity
    
    backends: [azure, lambda]  # (Optional) Use only listed backends 

    default: true # (Optional) Activate the profile by default
```

</div>

You can mark any profile as default or pass its name via `--profile` to `dstack run`.

## YAML reference

#SCHEMA# dstack._internal.core.models.profiles.Profile
    overrides:
      max_price:
        type: 'Optional[float]'


#SCHEMA# dstack._internal.core.models.profiles.ProfileResources
    overrides:
      memory:
        default: 8GB

#SCHEMA# dstack._internal.core.models.profiles.ProfileGPU

#SCHEMA# dstack._internal.core.models.profiles.ProfileRetryPolicy
