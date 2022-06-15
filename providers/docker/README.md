# dstack docker provider

This provider runs a Docker image on a single machine with required resources.

## Workflow

Example:

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
      cpu: 1
      memory: 1GB
```

Here's the list of all parameters supported by the provider:

| Parameter                 | Required | Description                                                          |
|---------------------------|----------|----------------------------------------------------------------------|
| `image`                   | Yes      | The Docker image                                                     |
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


## Command line 

```bash
usage: dstack run docker [-h] [-e [ENV]] [--artifact [ARTIFACT]]
                         [--working-dir [WORKING_DIR]] [--ports [PORTS]]
                         [--cpu [CPU]] [--memory [MEMORY]] [--gpu [GPU]]
                         [--gpu-name [GPU_NAME]] [--gpu-memory [GPU_MEMORY]]
                         [--shm-size [SHM_SIZE]]
                         IMAGE [COMMAND] [ARGS ...]
```

Example:

```bash
dstack run docker --artifact output --cpu 1 --memory 1GB ubuntu
```