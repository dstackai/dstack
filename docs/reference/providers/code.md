# code

The `code` provider launches a VS Code dev environment.

It comes with Python and Conda pre-installed. 

If GPU is requested, the provider pre-installs the CUDA driver too.

## Usage example 

<div editor-title=".dstack/workflows/code-example.yaml">

```yaml
workflows:
  - name: ide
    provider: code
    artifacts:
      - path: ./output
    resources:
      interruptible: true
      gpu: 1
```

</div>

To run this workflow, use the following command:

<div class="termy">

```shell
$ dstack run ide
```

</div>

## Properties reference

The following properties are optional:

- `setup` - (Optional) The list of shell commands to run before running the Python file
- `python` - (Optional) The major version of Python
- `environment` - (Optional) The list of environment variables 
- [`artifacts`](#artifacts) - (Optional) The list of output artifacts
- [`resources`](#resources) - (Optional) The hardware resources required by the workflow
- `working_dir` - (Optional) The path to the working directory
- `ssh` - (Optional) Runs SSH server in the container if `true`
- `cache` - (Optional) The list of directories to cache between runs

### artifacts

The list of output artifacts

- `path` – (Required) The relative path of the folder that must be saved as an output artifact
- `mount` – (Optional) `true` if the artifact files must be saved in real-time.
    Must be used only when real-time access to the artifacts is important: 
    for storing checkpoints (e.g. if interruptible instances are used) and event files
    (e.g. TensorBoard event files, etc.)
    By default, it's `false`.

### resources

The hardware resources required by the workflow

- `cpu` - (Optional) The number of CPU cores
- `memory` (Optional) The size of RAM memory, e.g. `"16GB"`
- [`gpu`](#gpu) - (Optional) The number of GPUs, their model name and memory
- `shm_size` - (Optional) The size of shared memory, e.g. `"8GB"`
- `interruptible` - (Optional) `true` if you want the workflow to use interruptible instances.
    By default, it's `false`.
- `remote` - (Optional) `true` if you want the workflow to run in the cloud.
   By default, it's `false`.

!!! info "NOTE:"
    If your workflow is using parallel communicating processes (e.g. dataloaders in PyTorch), 
    you may need to configure the size of the shared memory (`/dev/shm` filesystem) via the `shm_size` property.

### gpu

The number of GPUs, their name and memory

- `count` - (Optional) The number of GPUs
- `memory` (Optional) The size of GPU memory, e.g. `"16GB"`
- `name` (Optional) The name of the GPU model (e.g. `"K80"`, `"V100"`, etc)