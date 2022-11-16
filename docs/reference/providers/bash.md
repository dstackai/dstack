# bash

The `bash` provider runs given shell commands. 

It comes with Python and Conda pre-installed, and allows to expose ports. 

If GPU is requested, the provider pre-installs the CUDA driver too.

## Usage example

```yaml
workflows:
  - name: "train"
    provider: bash
    deps:
      - tag: some_tag
    python: 3.10
    commands:
      - pip install requirements.txt
      - python src/train.py
    artifacts: 
      - path: ./checkpoint
    resources:
      interruptible: true
      gpu: 1
```

## Properties reference

The following properties are required:

- `commands` - (Required) The shell commands to run

The following properties are optional:

- `before_run` - (Optional) The list of shell commands to run before running the main commands
- `requirements` - (Optional) The path to the `requirements.txt` file
- `python` - (Optional) The major version of Python. By default, it's `3.10`.
- `env` - (Optional) The list of environment variables 
- [`artifacts`](#artifacts) - (Optional) The list of output artifacts
- [`resources`](#resources) - (Optional) The hardware resources required by the workflow
- `working_dir` - (Optional) The path to the working directory

#### artifacts

The list of output artifacts

- `path` – (Required) The relative path of the folder that must be saved as an output artifact
- `mount` – (Optional) `true` if the artifact files must be saved in real-time.
    Must be used only when real-time access to the artifacts is important. 
    For example, for storing checkpoints when interruptible instances are used, or for storing
    event files in real-time (e.g. TensorBoard event files.)
    By default, it's `false`.

#### resources

The hardware resources required by the workflow

- `cpu` - (Optional) The number of CPU cores
- `memory` (Optional) The size of RAM memory, e.g. `"16GB"`
- [`gpu`](#gpu) - (Optional) The number of GPUs, their model name and memory
- `shm_size` - (Optional) The size of shared memory, e.g. `"8GB"`
- `interruptible` - (Optional) `true` if you want the workflow to use interruptible instances.
    By default, it's `false`.
- `local` - (Optional) `true` if you want the workflow to run locally. Requires Docker
  or [NVIDIA Docker](https://github.com/NVIDIA/nvidia-docker) to be installed locally.
   By default, it's `false`.

!!! info "NOTE:"
    If your workflow is using parallel communicating processes (e.g. dataloaders in PyTorch), 
    you may need to configure the size of the shared memory (`/dev/shm` filesystem) via the `shm_size` property.

#### gpu

The number of GPUs, their name and memory

- `count` - (Optional) The number of GPUs
- `memory` (Optional) The size of GPU memory, e.g. `"16GB"`
- `name` (Optional) The name of the GPU model (e.g. `"K80"`, `"V100"`, etc)

## More examples

#### Ports

If you'd like your workflow to expose ports, you have to specify the `ports` property with the number
of ports to expose. Actual ports will be assigned on startup and passed to the workflow via the environment
variables `PORT_<number>`.

```yaml
workflows:
  - name: app
    provider: bash
    ports: 1
    commands: 
      - pip install -r requirements.txt
      - gunicorn main:app --bind 0.0.0.0:$PORT_0
```