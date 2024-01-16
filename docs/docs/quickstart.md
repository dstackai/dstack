# Quickstart

## Define a configuration

First, create a YAML file in your project folder. Its name must end with `.dstack.yml` (e.g. `.dstack.yml` or `train.dstack.yml`
are both acceptable).

=== "Dev environment"

    <div editor-title=".dstack.yml"> 

    ```yaml
    type: dev-environment

    python: "3.11" # (Optional) If not specified, your local version is used
    
    ide: vscode
    ```

    </div>

    A dev environments is a perfect tool for interactive experimentation with your IDE.
    It allows to pre-configure the Python version or a Docker image, etc.
    Go to [Dev environments](concepts/dev-environments.md) to learn more.

=== "Task"

    <div editor-title="train.dstack.yml"> 

    ```yaml
    type: task

    python: "3.11" # (Optional) If not specified, your local version is used
    
    commands:
      - pip install -r requirements.txt
      - python train.py
    ```

    </div>

    A task may run training scripts, batch jobs, or web apps. It allows to specify the commands, ports, 
    and pre-configure the Python version or a Docker image, etc. Go to [Tasks](concepts/tasks.md) to learn more.

=== "Service"

    <div editor-title="serve.dstack.yml"> 

    ```yaml
    type: service

    image: ghcr.io/huggingface/text-generation-inference:latest
    
    env: 
      - MODEL_ID=TheBloke/Llama-2-13B-chat-GPTQ 
    
    port: 80
    
    commands:
      - text-generation-launcher --hostname 0.0.0.0 --port 80 --trust-remote-code
    ```
    
    </div>

    A service makes it very easy to deploy models or web apps. It allows to specify the commands, 
    and the Python version or a Docker image, etc. Go to [Services](concepts/services.md) to learn more.

## Run configuration

To run a configuration, use the `dstack run` command followed by the working directory path, 
configuration file path, and any other options (e.g., for requesting hardware resources).

<div class="termy">

```shell
$ dstack run . -f train.dstack.yml --gpu A100

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

No need to worry about copying code, setting up environment, IDE, etc. `dstack` handles it all 
automatically.

## What's next?

1. Learn more about [dev environments](concepts/dev-environments.md), [tasks](concepts/tasks.md), 
    and [services](concepts/services.md)
2. Browse [examples](../examples/index.md)
3. Join the [Discord server](https://discord.gg/u8SmfwPpMd)