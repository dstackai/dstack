# dstack python provider

This provider runs a Python script on a single machine with required resources.

Here's the list of parameters supported by the provider:

| Parameter                 | Required | Description                                                          |
|---------------------------|----------|----------------------------------------------------------------------|
| `script`                  | Yes      | The Python script to run                                             |
| `args`                    | No       | The arguments for the Python script                                  |
| `requirements`            | No       | The list of Python packages required by the script                   |
| `version`                 | No       | The major Python version. By default, it's `3.10`.                   |
| `environment`             | No       | The list of environment variables and their values                   |
| `artifacts`               | No       | The list of output artifacts                                         |
| `resources`               | No       | The resources required to run the workflow                           |
| `resources.cpu`           | No       | The required number of CPUs                                          |
| `resources.memory`        | No       | The required amount of memory                                        |
| `resources.gpu`           | No       | The required number of GPUs                                          |
| `resources.gpu.name`      | No       | The name of the GPU brand (e.g. "V100", etc.)                        |
| `resources.gpu.count`     | No       | The required number of GPUs                                          |
| `resources.interruptible` | No       | `True` if the workflow can be interrupted. By default, it's `False`. |

Example:

```yaml
workflows:
  - name: download-model  
    provider: python
    requirements: requirements.txt
    script: download_model.py
    environment:
      PYTHONPATH: src
    artifacts:
      - models
    resources:
      cpu: 2
      memory: 32GB
      gpu: 1
```