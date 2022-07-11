# Docker

This provider runs a Docker image. 

You can specify an image, a list of bash commands to run inside the container, 
environment variables, arguments, which folders to save as output artifacts, dependencies to
other workflows if any, and the resources the workflow needs (e.g. CPU, GPU, memory, etc).

## Example usage 

### Basic example

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: train
        provider: docker
        image: ubuntu
        commands:
          - mkdir -p output
          - echo 'Hello, world!' > output/hello.txt
        artifacts: ["output"]
        resources:
          gpu:
            name: "K80"
            count: 1
    ```

Alternatively, you can use this provider from the CLI (without defining your workflow
in the `.dstack/workflows.yaml` file):

```bash
dstack run docker \
  -c "mkdir -p output && echo 'Hello, world!' > output/hello.txt" \
  -a output --gpu-name K80
```

[//]: # (TODO: Environment variables)

[//]: # (TODO: Resources)

## Argument reference

### Workflows file

The following arguments are required:

- `file` - (Required) The Python file to run

The following arguments are optional:

- `args` - (Optional) The list of arguments for the Python program
- `before_run` - (Optional) The list of shell commands to run before running the Python file
- `requirements` - (Optional) The path to the `requirements.txt` file
- `version` - (Optional) The major version of Python. By default, it's `3.10`.
- `environment` - (Optional) The list of environment variables 
- `artifacts` - (Optional) The list of folders that must be saved as output artifacts
- [`resources`](#resources) - (Optional) The hardware resources required by the workflow
- `working_dir` - (Optional) The path to the working directory

#### resources

The hardware resources required by the workflow

- `cpu` - (Optional) The number of CPU cores
- `memory` (Optional) The size of RAM memory, e.g. `"16GB"`
- [`gpu`](#gpu) - (Optional) The number of GPUs, their model name and memory
- `shm_size` - (Optional) The size of shared memory, e.g. `"8GB"`
- `interruptible` - (Optional) `true` if the workflow can run on interruptible instances.
    By default, it's `false`.

#### gpu

The number of GPUs, their name and memory

- `count` - (Optional) The number of GPUs
- `memory` (Optional) The size of GPU memory, e.g. `"16GB"`
- `name` (Optional) The name of the GPU model (e.g. `"K80"`, `"V100"`, etc)

### CLI

```bash
usage: dstack run docker [-h] [-r [REQUIREMENTS]] [-e [ENV]] [-a [ARTIFACT]]
                         [--working-dir [WORKING_DIR]] [-i] [--cpu [CPU]]
                         [--memory [MEMORY]] [--gpu [GPU]]
                         [--gpu-name [GPU_NAME]] [--gpu-memory [GPU_MEMORY]]
                         [--shm-size [SHM_SIZE]] [--ports [PORTS]]
                         [-c [COMMAND]]
                         IMAGE
```

The following arguments are required:

- `IMAGE` - (Required) The Docker image to run

The following arguments are optional:

- `-r [REQUIREMENTS]`, `--requirements [REQUIREMENTS]` - (Optional) The path to the `requirements.txt` file
- `--working-dir [WORKING_DIR]` - (Optional) The path to the working directory
- `-e [ENV]`, `--env [ENV]` - (Optional) The list of environment variables 
- `-a [ARTIFACT]`, `--artifact [ARTIFACT]` - (Optional) A folder that must be saved as output artifact
- `--cpu [CPU]` - (Optional) The number of CPU cores
- `--memory [MEMORY]` - The size of RAM memory, e.g. `"16GB"`
- `--gpu [GPU]` - (Optional) The number of GPUs
- `--gpu-name [GPU_NAME]` - (Optional) The name of the GPU model (e.g. `"K80"`, `"V100"`, etc)
- `--gpu-memory [GPU_MEMORY]` - (Optional) The size of GPU memory, e.g. `"16GB"`
- `--shm-size [SHM_SIZE]` - (Optional) The size of shared memory, e.g. `"8GB"`
- `-i`, `--interruptible` - (Optional) if the workflow can run on interruptible instances.

[//]: # (TODO: Add --dep argument)

[//]: # (TODO: Tell about ports)