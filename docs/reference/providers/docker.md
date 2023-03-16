# docker

The `docker` provider runs given shell commands using a given Docker image.

Unlike the `bash`, `code`, `lab`, and `notebook` providers, the `docker` provider doesn't  
pre-install Python, Conda, or the CUDA driver.

If you plan to build your own Docker image, you can base it on the [`dstackai/miniforge`](https://hub.docker.com/repository/docker/dstackai/miniforge) 
Docker image that has Conda and the CUDA driver pre-installed.

## Usage example 

Inside the `.dstack/workflows` directory within your project, create the following `docker-example.yaml` file:

```yaml
workflows:
  - name: hello-docker
    provider: docker
    image: ubuntu
    entrypoint: /bin/bash -i -c
    commands:
      - mkdir -p output
      - echo 'Hello, world!' > output/hello.txt
    artifacts:
      - path: ./output
    resources:
      gpu:
        name: "K80"
        count: 1
```

To run this workflow, use the following command:

```shell
dstack run hello-docker
```

## Properties reference

The following properties are required:

- `image` - (Required) The Docker image name

The following properties are optional:

- `commands` - (Optional) The list of bash commands. If any - entrypoint is overridden with `/bin/sh -i -c`
- `entrypoint` - (Optional) The entrypoint string to override the image entrypoint
- `version` - (Optional) The major version of Python
- `environment` - (Optional) The list of environment variables 
- [`artifacts`](#artifacts) - (Optional) The list of output artifacts
- [`resources`](#resources) - (Optional) The hardware resources required by the workflow
- `working_dir` - (Optional) The path to the working directory

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