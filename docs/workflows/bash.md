# bash

The `bash` provider runs given shell commands. 

The provider allows you to specify commands, a version of Python (if you want it to be pre-installed), 
a `requirements.txt` file (if you want them to be pre-installed), environment variables, the number of ports to expose (if needed), 
which folders to save as output artifacts, dependencies to other workflows if any, and the resources the workflow needs 
(e.g. whether it should be a spot/preemptive instance, how much memory, GPU, etc.) 

## Basic example

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: "train"
        provider: bash
        deps:
          - :some_tag
        python: 3.10
        env: 
          - PYTHONPATH=src
        commands:
          - pip install requirements.txt
          - python src/train.py
        artifacts: 
          - path: checkpoint
        resources:
          interruptible: true
          gpu: 1
    ```

## Workflow syntax

The following properties are required:

- `commands` - (Required) The shell commands to run

The following properties are optional:

- `before_run` - (Optional) The list of shell commands to run before running the main commands
- `requirements` - (Optional) The path to the `requirements.txt` file
- `python` - (Optional) The major version of Python. By default, it's `3.10`.
- `env` - (Optional) The list of environment variables 
- `artifacts` - (Optional) The list of folders that must be saved as output artifacts
- [`resources`](#resources) - (Optional) The hardware resources required by the workflow
- `working_dir` - (Optional) The path to the working directory

#### resources

The hardware resources required by the workflow

- `cpu` - (Optional) The number of CPU cores
- `memory` (Optional) The size of RAM memory, e.g. `"16GB"`
- [`gpu`](#gpu) - (Optional) The number of GPUs, their model name and memory
- `shm_size` - (Optional) The size of shared memory, e.g. `"8GB"`
- `interruptible` - (Optional) `true` if the instance must be spot/preemptive.
    By default, it's `false`.

#### gpu

The number of GPUs, their name and memory

- `count` - (Optional) The number of GPUs
- `memory` (Optional) The size of GPU memory, e.g. `"16GB"`
- `name` (Optional) The name of the GPU model (e.g. `"K80"`, `"V100"`, etc)

!!! info "NOTE:"
    The instances are automatically configured with the correct CUDA driver to use NVIDIA GPUs.

## Ports example

If you'd like your workflow to expose ports, you have to specify the `ports` property with the number
of ports to expose. Actual ports will be assigned on startup and passed to the workflow via the environment
variables `PORT_<number>`.

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: app
        provider: bash
        ports: 1
        commands: 
          - pip install -r requirements.txt
          - gunicorn main:app --bind 0.0.0.0:$PORT_0
    ```

!!! info "NOTE:"
    If you need, you can also refer to the actual hostname of the workflow via the environment variable `HOSTNAME`.