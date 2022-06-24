# dstack streamlit provider

This provider runs a Streamlit application on a single machine with required resources.

# Workflow

Example:

```yaml
workflows:
  - name: streamlit  
    provider: streamlit
    target: app.py
    depends
    resources:
      gpu: 1
```

Here's the list of parameters supported by the provider:

| Parameter                 | Required | Description                                                          |
|---------------------------|----------|----------------------------------------------------------------------|
| `target`                  | Yes      | The path or a URL that points to the Python script                   |
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

## Command line

usage: dstack run streamlit [-h] [-r [REQUIREMENTS]] [-e [ENV]]
                         [--artifact [ARTIFACT]] [--working-dir [WORKING_DIR]]
                         [--cpu [CPU]] [--memory [MEMORY]] [--gpu [GPU]]
                         [--gpu-name [GPU_NAME]] [--gpu-memory [GPU_MEMORY]]
                         [--shm-size [SHM_SIZE]]
                         TARGET [ARGS ...]

Example:

```bash
dstack run streamlit app.py --gpu 1
```