# profiles.yml

Profiles configure the project to use and the resources required for the run.

Profiles are defined in the `.dstack/profiles.yml` file within your project directory.

Below is a full reference of all available properties.

- `profiles` (Required) - The root property (of an `array` type)
    - `name` - (Required) The name of the profile
    - `resources` - (Optional) The minimum required resources
        - `memory` - (Optional) The minimum size of RAM memory (e.g., `"16GB"`). 
        - `gpu` - (Optional) The minimum number of GPUs, their model name and memory
            - `name` - (Optional) The name of the GPU model (e.g. `"K80"`, `"V100"`, `"A100"`, etc)
            - `count` - (Optional) The minimum number of GPUs. Defaults to `1`.
            - `memory` (Optional) The minimum size of GPU memory (e.g., `"16GB"`)
        - `shm_size` (Optional) The size of shared memory (e.g., `"8GB"`). If you are using parallel communicating
          processes (e.g., dataloaders in PyTorch), you may need to configure this.
    - `instance-type` - (Optional) The type of instance. Can be `auto`, `on-demand`, and `spot`. Defaults to `auto`.

[//]: # (TODO: Add examples)

[//]: # (TODO: Explain how `instance-type` works)

[//]: # (TODO: Add more explanations of how it works, incl. how to pass defined profiles to the CLI)