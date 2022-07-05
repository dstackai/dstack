<div align="center">
<img src="/docs/assets/logo.svg" width="200px"/>    

A provider that runs a Docker image
______________________________________________________________________

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

</div>

# About

This provider runs a Docker image. You can specify an image, a bash command to run inside the container,
environment variables, specify which folders to save as output artifacts,
dependencies to other workflows if any, and finally the resources the container needs (CPU, GPU, memory, etc).

## Workflows

Here's how to use this provider in `.dstack/workflows.yaml`:

```yaml
workflows:
  - name: hello
    provider: docker
    image: ubuntu
    commands:
      - mkdir -p output
      - echo 'Hello, world!' > output/hello.txt
    artifacts:
      - output
    resources:
      gpu: 1
```

<details>
<summary>All workflow parameters supported by the provider</summary>

| Parameter                 | Required | Description                                                          |
|---------------------------|----------|----------------------------------------------------------------------|
| `image`                   | Yes      | The Docker image                                                     |
| `before_run`              | No       | The list of commands to run before the main commands                 |
| `commands`                | No       | The list of commands to run                                          |
| `ports`                   | No       | The number of ports to expose                                        |
| `artifacts`               | No       | The list of output artifacts                                         |
| `resources`               | No       | The resources required to run the workflow                           |
| `resources.cpu`           | No       | The required number of CPUs                                          |
| `resources.memory`        | No       | The required amount of memory                                        |
| `resources.gpu`           | No       | The required number of GPUs                                          |
| `resources.gpu.name`      | No       | The name of the GPU brand (e.g. "V100", etc.)                        |
| `resources.gpu.count`     | No       | The required number of GPUs                                          |
| `resources.interruptible` | No       | `True` if the workflow can be interrupted. By default, it's `False`. |
</details>

## Command line 

Here's how to use this provider from the command line:

```bash
usage: dstack run docker [-h] [-e [ENV]] [-a [ARTIFACT]]
                         [--working-dir [WORKING_DIR]] [--ports [PORTS]]
                         [--cpu [CPU]] [--memory [MEMORY]] [--gpu [GPU]]
                         [--gpu-name [GPU_NAME]] [--gpu-memory [GPU_MEMORY]]
                         [--shm-size [SHM_SIZE]]
                         IMAGE [COMMAND] [ARGS ...]
```

Example:

```bash
dstack run docker hello-world
```