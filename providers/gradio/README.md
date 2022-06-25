<div align="center">
<img src="/docs/assets/logo.svg" width="200px"/>    

A provider that launches a Gradio application
______________________________________________________________________

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

</div>

# About

This provider launches a Gradio application. You can specify a file with requirements, a version of Gradio, 
a version of Python, provide environment variables and arguments to your application, 
specify which folders to save as output artifacts,
dependencies to other workflows if any, and finally the resources the application needs (CPU, GPU, memory, etc).

# Workflows

Example:

```yaml
workflows:
  - name: app  
    provider: gradio
    file: app.py
    resources:
      gpu: 1
```

<details>
<summary>All workflow parameters supported by the provider</summary>

| Parameter                 | Required | Description                                                          |
|---------------------------|----------|----------------------------------------------------------------------|
| `file`                    | Yes      | The path to the Python script                                        |
| `requirements`            | No       | The list of Python packages to pre-install                           |
| `version`                 | No       | The Gradio version                                                   |
| `python`                  | No       | The major Python version. By default, it's `3.10`.                   |
| `environment`             | No       | The list of environment variables and their values                   |
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
usage: dstack run gradio [-h] [-r [REQUIREMENTS]] [-e [ENV]]
                         [-a [ARTIFACT]] [--working-dir [WORKING_DIR]]
                         [--cpu [CPU]] [--memory [MEMORY]] [--gpu [GPU]]
                         [--gpu-name [GPU_NAME]] [--gpu-memory [GPU_MEMORY]]
                         [--shm-size [SHM_SIZE]]
                         FILE [ARGS ...]
```

Example:

```bash
dstack run gradio app.py -r requirements.txt --gpu 1
```