# Quickstart

!!! info "Installation"
    Before using `dstack`, either set up the open-source server, or sign up
    with `dstack Sky`.
    See [Installation](installation/index.md) for more details.
    
## Initialize a repo

To use `dstack`'s CLI in a folder, first run [`dstack init`](reference/cli/index.md#dstack-init) within that folder.

<div class="termy">

```shell
$ mkdir quickstart && cd quickstart
$ dstack init
```

</div>

Your folder can be a regular local folder or a Git repo.

## Define a configuration

Define what you want to run as a YAML file. The filename must end with `.dstack.yml` (e.g., `.dstack.yml`
or `train.dstack.yml` are both acceptable).

=== "Dev environment"

    Dev environments allow you to quickly provision a machine with a pre-configured environment, resources, IDE, code, etc.

    <div editor-title=".dstack.yml"> 

    ```yaml
    type: dev-environment

    # Use either `python` or `image` to configure environment
    python: "3.11"
    # image: ghcr.io/huggingface/text-generation-inference:latest
    
    ide: vscode

    # (Optional) Configure `gpu`, `memory`, `disk`, etc
    resources:
      gpu: 24GB
    ```

    </div>

=== "Task"

    Tasks make it very easy to run any scripts, be it for training, data processing, or web apps. They allow you to pre-configure the environment, resources, code, etc.

    <div editor-title="train.dstack.yml"> 

    ```yaml
    type: task

    python: "3.11"
    env:
      - HF_HUB_ENABLE_HF_TRANSFER=1
    commands:
      - pip install -r fine-tuning/qlora/requirements.txt
      - python fine-tuning/qlora/train.py

    # (Optional) Configure `gpu`, `memory`, `disk`, etc
    resources:
      gpu: 24GB
    ```

    </div>

    Ensure `requirements.txt` and `train.py` are in your folder. You can take them from [`examples`](https://github.com/dstackai/dstack/tree/master/examples/fine-tuning/qlora).

=== "Service"

    Services make it easy to deploy models and apps cost-effectively as public endpoints, allowing you to use any frameworks.

    <div editor-title="serve.dstack.yml"> 

    ```yaml
    type: service

    image: ghcr.io/huggingface/text-generation-inference:latest
    env:
      - HUGGING_FACE_HUB_TOKEN # required to run gated models
      - MODEL_ID=mistralai/Mistral-7B-Instruct-v0.1
    commands:
      - text-generation-launcher --port 8000 --trust-remote-code
    port: 8000

    # (Optional) Configure `gpu`, `memory`, `disk`, etc
    resources:
      gpu: 24GB
    ```

    </div>

## Run configuration

Run a configuration using the [`dstack run`](reference/cli/index.md#dstack-run) command, followed by the working directory path (e.g., `.`), 
and the path to the configuration file.

<div class="termy">

```shell
$ dstack run . -f train.dstack.yml

 BACKEND     REGION         RESOURCES                     SPOT  PRICE
 tensordock  unitedkingdom  10xCPU, 80GB, 1xA100 (80GB)   no    $1.595
 azure       westus3        24xCPU, 220GB, 1xA100 (80GB)  no    $3.673
 azure       westus2        24xCPU, 220GB, 1xA100 (80GB)  no    $3.673
 
Continue? [y/n]: y

Provisioning...
---> 100%

Epoch 0:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
Epoch 1:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
Epoch 2:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
```

</div>

The `dstack run` command automatically uploads your code, including any local uncommitted changes. 
To exclude any files from uploading, use `.gitignore`.

## What's next?

1. Read about [dev environments](dev-environments.md), [tasks](tasks.md), 
    [services](services.md), and [fleets](fleets.md) 
2. Browse [examples :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/tree/master/examples){:target="_blank"}
3. Join the community via [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd)