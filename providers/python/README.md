# dstack python provider

This provider runs a Python script on a single machine with required resources.

Here's the list of parameters supported by the provider:

| Parameter       | Required | Description                                            |
|-----------------|----------|--------------------------------------------------------|
| `python_script` | Yes      | The Python script with arguments.                      |
| `requirements`  | No       | The list of Python packages required by the script.    |
| `python`        | No       | The major Python version. By default, is `3.10`.       |
| `environment`   | No       | The list of environment variables and their values.    |
| `artifacts`     | No       | The list of output artifacts.                          |
| `resources`     | No       | The CPU, memory, and GPU required to rin the workflow. |

Example:

```bash
workflows:
  - name: download-model  
    provider: python
    requirements: requirements.txt
    python_script: download_model.py
    environment:
      PYTHONPATH: src
    artifacts:
      - models
    resources:
      cpu: 2
      memory: 32GB
      gpu: 1
```