<div align="center">
<img src="/docs/assets/logo.svg" width="200px"/>    

A provider that launches a Streamlit application
______________________________________________________________________

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

</div>

# About

This provider launches a Streamlit application. You can specify a file with requirements, a version of Streamlit, 
a version of Python, provide environment variables and arguments to your application, 
specify which folders to save as output artifacts,
dependencies to other workflows if any, and finally the resources the application needs (CPU, GPU, memory, etc).

# Workflows

Example:

```yaml
workflows:
  - name: app  
    provider: streamlit
    target: app.py
    resources:
      gpu: 1
```

<details>
<summary>All workflow parameters supported by the provider</summary>

| Parameter                 | Required | Description                                                          |
|---------------------------|----------|----------------------------------------------------------------------|
| `target`                  | Yes      | The path or a URL that points to the Python script                   |
| `before_run`              | No       | The list of commands to run before launching the app                 |
| `requirements`            | No       | The list of Python packages to pre-install                           |
| `version`                 | No       | The Streamlit version                                                |
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
usage: dstack run streamlit [-h] [-r [REQUIREMENTS]] [-e [ENV]]
                         [-a [ARTIFACT]] [--working-dir [WORKING_DIR]]
                         [--cpu [CPU]] [--memory [MEMORY]] [--gpu [GPU]]
                         [--gpu-name [GPU_NAME]] [--gpu-memory [GPU_MEMORY]]
                         [--shm-size [SHM_SIZE]]
                         TARGET [ARGS ...]
```

Example:

```bash
dstack run streamlit app.py -r requirements.txt --gpu 1
```