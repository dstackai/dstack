# profiles.yml

Profiles configure the project to use and the resources required for the run.

Profiles are defined in the `.dstack/profiles.yml` file within your project directory.

Below is a full reference of all available properties.

- `profiles` (Required) - The root property (of an `array` type)
    - `name` - (Required) The name of the profile
    - `resources` - (Optional) The minimum required resources
        - `memory` - (Optional) The minimum size of RAM memory (e.g., `"16GB"`). 
        - `gpu` - (Optional) The minimum number of GPUs, their model name and memory
            - `name` - (Optional) The name of the GPU model (e.g., `"K80"`, `"V100"`, `"A100"`, etc)
            - `count` - (Optional) The minimum number of GPUs. Defaults to `1`.
            - `memory` (Optional) The minimum size of GPU memory (e.g., `"16GB"`)
        - `shm_size` (Optional) The size of shared memory (e.g., `"8GB"`). If you are using parallel communicating
          processes (e.g., dataloaders in PyTorch), you may need to configure this.
    - `spot_policy` - (Optional) The policy for provisioning spot or on-demand instances: `spot`, `on-demand`, or `auto`. `spot` provisions a spot instance. `on-demand` provisions a on-demand instance. `auto` first tries to provision a spot instance and then tries on-demand if spot is not available. Defaults to `on-demand` for dev environments and to `auto` for tasks.
    - `retry_policy` - (Optional) The policy for re-submitting the run.
        - `retry` - (Optional) Whether to retry the run on failure or not. Default to `false`
        - `limit` - (Optional) The maximum period of retrying the run, e.g., `4h` or `1d`. Defaults to `1h` if `retry` is `true`.
    - `max_duration` - (Optional) The maximum duration of a run (e.g., `2h`, `1d`, etc). After it elapses, the run is forced to stop. Protects from running idle instances. Defaults to `6h` for dev environments and to `72h` for tasks. Use `max_duration: off` to disable maximum run duration.

[//]: # (TODO: Add examples)

[//]: # (TODO: Add more explanations of how it works, incl. how to pass defined profiles to the CLI)