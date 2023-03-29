# bash

The `bash` provider runs given shell commands. 

It comes with Python and Conda pre-installed, and allows to expose ports. 

If GPU is requested, the provider pre-installs the CUDA driver too.

## Usage example

<div editor-title=".dstack/workflows/bash-example.yaml"> 

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

</div>

To run this workflow, use the following command:

<div class="termy">

```shell
$ dstack run train
```

</div>

## Properties reference

The following properties are required:

- `commands` - (Required) The shell commands to run

The following properties are optional:

- `python` - (Optional) The major version of Python
- `env` - (Optional) The list of environment variables 
- [`artifacts`](#artifacts) - (Optional) The list of output artifacts
- [`resources`](#resources) - (Optional) The hardware resources required by the workflow
- `working_dir` - (Optional) The path to the working directory
- `ssh` - (Optional) Runs SSH server in the container if `true`

### artifacts

The list of output artifacts

- `path` – (Required) The relative path of the folder that must be saved as an output artifact
- `mount` – (Optional) `true` if the artifact files must be saved in real-time.
    Must be used only when real-time access to the artifacts is important. 
    For example, for storing checkpoints when interruptible instances are used, or for storing
    event files in real-time (e.g. TensorBoard event files.)
    By default, it's `false`.

### resources

The hardware resources required by the workflow

- `cpu` - (Optional) The number of CPU cores
- `memory` (Optional) The size of RAM memory, e.g. `"16GB"`
- [`gpu`](#gpu) - (Optional) The number of GPUs, their model name and memory
- `shm_size` - (Optional) The size of shared memory, e.g. `"8GB"`
- `interruptible` - (Optional) `true` if you want the workflow to use interruptible instances.
    By default, it's `false`.
- `remote` - (Optional) `true` if you want the workflow to run in the cloud.
   By default, it's `false`.

!!! info "NOTE:"
    If your workflow is using parallel communicating processes (e.g. dataloaders in PyTorch), 
    you may need to configure the size of the shared memory (`/dev/shm` filesystem) via the `shm_size` property.

### gpu

The number of GPUs, their name and memory

- `count` - (Optional) The number of GPUs
- `memory` (Optional) The size of GPU memory, e.g. `"16GB"`
- `name` (Optional) The name of the GPU model (e.g. `"K80"`, `"V100"`, etc)

## More examples

### Ports

If you'd like your workflow to expose ports, you have to specify the `ports` property with the number
of ports to expose. Actual ports will be assigned on startup and passed to the workflow via the environment
variables `PORT_<number>`.

<div editor-title=".dstack/workflows/app-example.yaml">

```yaml
workflows:
  - name: app
    provider: bash
    ports: 1
    commands: 
      - pip install -r requirements.txt
      - gunicorn main:app --bind 0.0.0.0:$PORT_0
```

</div>

### Background processes

Similar to the regular `bash` shell, the `bash` provider permits the execution of background processes. This can be achieved
by appending `&` to the respective command.

Here's an example:

<div editor-title=".dstack/workflows/ping-background.yaml">

```yaml
workflows:
  - name: train-with-tensorboard
    provider: bash
    ports: 1
    commands:
      - pip install torchvision pytorch-lightning tensorboard
      - tensorboard --port $PORT_0 --host 0.0.0.0 --logdir lightning_logs &
      - python train.py
    artifacts:
      - path: lightning_logs
```

</div>

This example will run the `tensorboard` application in the background, enabling browsing of the logs of the training
job while it is in progress.