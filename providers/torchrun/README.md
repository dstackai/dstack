<div align="center">
<img src="/docs/assets/logo.svg" width="200px"/>    

A provider that runs a PyTorch training script on multiple nodes with GPU
______________________________________________________________________

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

</div>

# About

This provider runs a PyTorch training script on multiple nodes. You can specify a number of nodes, 
a training script, a file with requirements, aversion of Python,
provide environment variables and arguments to your training script, specify which folders to save as output artifacts,
and dependencies to other workflows if any, and finally the resources for each node (CPU, GPU, memory, etc).

## Workflows

Here's how to use this provider in `.dstack/workflows.yaml`:

```yaml
workflows:
  - name: train  
    provider: torchrun
    script: train.py
    requirements: requirements.txt
    artifacts:
      - checkpoint
    nodes: 4
    resources:
      gpu: 1
```

<details>
<summary>All workflow parameters supported by the provider</summary>

| Parameter                 | Required | Description                                                          |
|---------------------------|----------|----------------------------------------------------------------------|
| `script`                  | Yes      | The Python file to run                                               |
| `args`                    | No       | The arguments for the Python script                                  |
| `before_run`              | No       | The list of commands to run before running the script                |
| `requirements`            | No       | The list of Python packages required by the script                   |
| `version`                 | No       | The major Python version. By default, it's `3.10`.                   |
| `environment`             | No       | The list of environment variables and their values                   |
| `artifacts`               | No       | The list of output artifacts                                         |
| `nodes`                   | No       | The number of nodes to train on                                      |
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
usage: dstack run torchrun [-h] [-r [REQUIREMENTS]] [-e [ENV]]
                         [-a [ARTIFACT]] [--working-dir [WORKING_DIR]]
                         [--cpu [CPU]] [--memory [MEMORY]] [--gpu [GPU]]
                         [--gpu-name [GPU_NAME]] [--gpu-memory [GPU_MEMORY]]
                         [--shm-size [SHM_SIZE]] [--nnodes [NNODES]]
                         FILE [ARGS ...]
```

Example:

```bash
dstack run torchrun train.py -r requirements.txt -a checkpoint --nnodes 4 
```