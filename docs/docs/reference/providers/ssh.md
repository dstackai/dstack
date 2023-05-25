# ssh

The `ssh` provider runs ssh server inside the container and waits infinitely.

It comes with Python and Conda pre-installed, and allows to expose ports. 

If GPU is requested, the provider pre-installs the CUDA driver too.

## Usage example

To run instance with 1 GPU and print connection URI for VS Code

<div class="termy"> 

```shell
$ dstack run ssh --code --gpu 1
```

</div>

## Properties reference

The following properties are optional:

- `setup` - (Optional) The list of shell commands to run before idling
- `python` - (Optional) The major version of Python
- `env` - (Optional) The list of environment variables 
- [`artifacts`](#artifacts) - (Optional) The list of output artifacts
- [`resources`](#resources) - (Optional) The hardware resources required by the workflow
- [`ports`](#ports) - (Optional) The list of ports to expose
- `working_dir` - (Optional) The path to the working directory
- [`cache`](#cache) - (Optional) The list of directories to cache between runs

### artifacts

The list of output artifacts

- `path` – (Required) The relative path of the folder that must be saved as an output artifact
- `mount` – (Optional) `true` if the artifact files must be saved in real-time.
    Must be used only when real-time access to the artifacts is important. 
    For example, for storing checkpoints when interruptible instances are used, or for storing
    event files in real-time (e.g. TensorBoard event files.)
    By default, it's `false`.

### resources

The hardware resources required by the workflow

- `cpu` - (Optional) The number of CPU cores
- `memory` (Optional) The size of RAM memory, e.g. `"16GB"`
- [`gpu`](#gpu) - (Optional) The number of GPUs, their model name and memory
- `shm_size` - (Optional) The size of shared memory, e.g. `"8GB"`
- `interruptible` - (Optional) `true` if you want the workflow to use interruptible instances.
    By default, it's `false`.

!!! info "NOTE:"
    If your workflow is using parallel communicating processes (e.g. dataloaders in PyTorch), 
    you may need to configure the size of the shared memory (`/dev/shm` filesystem) via the `shm_size` property.

### gpu

The number of GPUs, their name and memory

- `count` - (Optional) The number of GPUs
- `memory` (Optional) The size of GPU memory, e.g. `"16GB"`
- `name` (Optional) The name of the GPU model (e.g. `"K80"`, `"V100"`, etc)

### cache

The list of directories to cache between runs

- `path` – (Required) The relative path of the folder that must be cached

## More examples

See more examples at [bash provider](bash.md#more-examples) page.
