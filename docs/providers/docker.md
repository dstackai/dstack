# docker

The `docker` provider runs a Docker image. 

The provider allows you to specify an image, a list of shell commands to run inside the container, 
environment variables, properties, which folders to save as output artifacts, dependencies to
other workflows if any, and the resources the workflow needs 
(e.g. whether it should be a spot/preemptive instance, how much memory, GPU, etc.) 

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
        artifacts:
          - path: output
        resources:
          gpu:
            name: "K80"
            count: 1
    ```

!!! info "NOTE:"
    Unlike the `bash`, `code`, `lab`, and `notebook` providers, the `docker` provider doesn't have 
    the CUDA driver and Conda pre-installed.

    If you want, you can use the [`dstackai/miniconda`](https://hub.docker.com/repository/docker/dstackai/miniconda) 
    base Docker image that has the CUDA driver and Conda pre-installed.

## Workflow syntax

The following properties are required:

- `file` - (Required) The Python file to run

The following properties are optional:

- `before_run` - (Optional) The list of shell commands to run before running the Docker image
- `requirements` - (Optional) The path to the `requirements.txt` file
- `version` - (Optional) The major version of Python. By default, it's `3.10`.
- `environment` - (Optional) The list of environment variables 
- [`artifacts`](#artifacts) - (Optional) The list of output artifacts
- [`resources`](#resources) - (Optional) The hardware resources required by the workflow
- `working_dir` - (Optional) The path to the working directory

#### artifacts

The list of output artifacts

- `path` – (Required) The relative path of the folder that must be saved as an output artifact
- `mount` – (Optional) `true` if the artifact files must be saved in real-time.
    Must be used only when real-time access to the artifacts is important: 
    for storing checkpoints (e.g. if interruptible instances are used) and event files
    (e.g. TensorBoard event files, etc.)
    By default, it's `false`.

#### resources

The hardware resources required by the workflow

- `cpu` - (Optional) The number of CPU cores
- `memory` (Optional) The size of RAM memory, e.g. `"16GB"`
- [`gpu`](#gpu) - (Optional) The number of GPUs, their model name and memory
- `shm_size` - (Optional) The size of shared memory, e.g. `"8GB"`
- `interruptible` - (Optional) `true` if the workflow can run on interruptible instances.
    By default, it's `false`.

!!! info "NOTE:"
    If your workflow is training a model using multiple parallel processes (e.g. via PyTorch DDP),
    make sure to use the `shm_size` to configure enough shared memory (e.g. `"8GB"` or more) so the processes 
    can communicate. Otherwise, you might get an error.

#### gpu

The number of GPUs, their name and memory

- `count` - (Optional) The number of GPUs
- `memory` (Optional) The size of GPU memory, e.g. `"16GB"`
- `name` (Optional) The name of the GPU model (e.g. `"K80"`, `"V100"`, etc)