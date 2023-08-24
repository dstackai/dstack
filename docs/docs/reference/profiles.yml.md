# profiles.yml

Instead of configuring resources, spot and retry policies, max price, and other parameters 
through [`dstack run`](cli/run.md), you can use profiles. 
To set up a profile, create the `.dstack/profiles.yml` file in the root folder of the project. 

## Usage example

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

### Schema reference

- <a href="#PROFILES"><code id="PROFILES">profiles</code></a> - (Required)
    - <a href="#NAME"><code id="NAME">name</code></a> - (Required) The name of the profile. Can be passed via [`--profile PROFILE`](cli/run.md#PROFILE) to `dstack run`
    - <a href="#RESOURCES"><code id="RESOURCES">resources</code></a> - (Optional)
        - <a href="#MEMORY"><code id="MEMORY">memory</code></a> - (Optional) The minimum size of memory. Example: `64GB` 
        - <a href="#GPU"><code id="GPU">gpu</code></a> - (Optional)
            - <a href="#NAME"><code id="NAME">name</code></a> - (Optional) The name of the GPU. Examples: `T4`, `V100`, `A10`, `L4`, `A100`, etc.)
            - <a href="#COUNT"><code id="COUNT">count</code></a> - (Optional) The minimum number of GPUs. Defaults to `1`.
            - <a href="#MEMORY"><code id="MEMORY">memory</code></a> - (Optional) The minimum size of GPU memory. Example: `20GB`
        - <a href="#SHM_SIZE"><code id="SHM_SIZE">shm_size</code></a> - (Optional) The size of shared memory. 
  Required to set if you are using parallel communicating processes. Example: `8GB`
    - <a href="#SPOT_POLICY"><code id="SPOT_POLICY">spot_policy</code></a> - (Optional) The spot policy. Example: `spot` (spot instances only), `on-demand` (on-demand instances only), or `auto` (spot if available or on-demand otherwise). Defaults to `on-demand` for dev environments and to `auto` for tasks and services.
    - <a href="#RETRY_POLICY"><code id="RETRY_POLICY">retry_policy</code></a> - (Optional) The policy for re-submitting the run.
        - <a href="#LIMIT"><code id="LIMIT">limit</code></a> - (Optional) The duration to wait for capacity. Example: `3h` or `2d`.
    - <a href="#MAX_DURATION"><code id="MAX_DURATION">max_duration</code></a> - (Optional) The maximum duration of a run. After it elapses, the run is forced to stop. Protects from running idle instances. Defaults to `6h` for dev environments and to `72h` for tasks. Examples: `3h` or `2d` or `off`.
    - <a href="#MAX_PRICE"><code id="MAX_PRICE">max_price</code></a> - (Optional) The maximum price per hour, in dollars. Example: `1.1` or `0.8`
    - <a href="#BACKENDS"><code id="BACKENDS">backends</code></a> - (Optional) Force using listed backends only. Possible values: `aws`, `azure`, `gcp`, `lambda`. If not specified, all configured backends are tried.
    - <a href="#DEFAULT"><code id="DEFAULT">default</code></a> - (Optional) If set to `true`, it will be activated by default