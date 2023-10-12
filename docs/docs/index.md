# Quickstart

`dstack` is an open-source toolkit for training, fine-tuning, and deployment of 
generative AI models across various cloud providers. (1)
{ .annotate } 

1. You can use various cloud accounts (e.g., AWS, GCP, Azure, Lambda Cloud) by configuring 
   their credentials. The framework can optimize costs by running workloads across multiple 
   regions and cloud accounts.

## Set up the server

Before using `dstack` through CLI or API, set up a `dstack` server. 

[//]: # (&#40;1&#41;)
[//]: # ({ .annotate } )

[//]: # (1.  The server manages your workloads' state and orchestrates them across configured cloud providers.)

### Install the server

The easiest way to install the server, is via `pip`:

<div class="termy">

```shell
$ pip install "dstack[all]" -U
```

</div>

### Configure clouds

Next, configure clouds via `~/.dstack/server/config.yml`. For format details, refer
to [Reference](reference/server/config.yml.md).

Example:

<div editor-title=".dstack/server/config.yml"> 

```yaml
projects:
- name: main
  backends:
  - type: aws
    regions: [us-east-1, eu-west-1]
    creds:
      access_key: ...
      secret_key: ...
```

</div>

[//]: # (!!! info "AWS, GCP, and Azure")
[//]: # (    If `~/.dstack/server/config.yml` doesn't exist but you default AWS, GCP, or )
[//]: # (    Azure credentials are configured on your machine, `dstack` will create the file automatically.)

### Start the server

To start the server, use the `dstack server` command:

<div class="termy">

```shell
$ dstack server

Applying configuration...
---> 100%

The server is running at http://127.0.0.1:3000/
```

</div>

[//]: # (TODO: Add a link to the Docker image)

## Using the CLI

The CLI allows running dev environments, tasks, and services, provided they are defined via YAML configuration files.

[//]: # (TODO: Mention how to configure the CLI)

### Init the repo

Before using the CLI in a folder, run [`dstack init`](reference/cli/init.md) inside it. (1)
{ .annotate } 

1.  When running dev environments, tasks, and services, `dstack` auto-uploads code from this folder to the cloud, including
uncommitted local changes. 

    To exclude files, list them in `.gitignore` (respected even if the folder isn't a Git repo).

<div class="termy">

```shell
$ mkdir quickstart && cd quickstart
$ dstack init
```

</div>

[//]: # (TODO: Optionally, mention Git credentials)

### Define the configuration

Configuration file names must end with `.dstack.yml` (e.g., `.dstack.yml` or `train.dstack.yml` are both acceptable).

#### Dev environments

A dev environment is a cloud instance pre-configured with an IDE.

Example:

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment

python: "3.11" # (Optional) If not specified, your local version is used

ide: vscode
```

</div>

After running it, `dstack` provides a URL to open the dev environment in your desktop VS Code.

[//]: # (TODO: Add a link to learn more about dev environments)

#### Tasks

A task can be a batch job or a web app.

Example:

<div editor-title="train.dstack.yml"> 

```yaml
type: task

python: "3.11" # (Optional) If not specified, your local version is used

ports:
  - 6006

commands:
  - pip install -r requirements.txt
  - tensorboard --logdir ./logs &
  - python train.py
```

</div>

??? info "Port forwarding"
    If you run a task, `dstack` forwards the configured ports to `localhost`.
    
    You can override the local port, for instance, by replacing `6006` with `"8080:6006"`. This will forward port `6006` 
    to `localhost:8080`.

[//]: # (TODO: Add a link to learn more about tasks)

#### Services

A service is a web app accessible from the Internet.

Example:

<div editor-title="service.dstack.yml"> 

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

!!! info "Gateway"
    Before you can run a service, you have to set up a [gateway](guides/services.md#set-up-a-gateway).

Running a service will make it available at `https://<run-name>.<your-domain>` using the
domain configured for the gateway.  

!!! info "Configuration options"
    Configuration files allow you to specify a custom Docker image, environment variables, and many other 
    options.
    For more details, refer to the [Reference](reference/dstack.yml/index.md).

[//]: # (TODO: Add a link to learn more about services)

### Run the configuration

The `dstack run` command requires the working directory path, and optionally, the `-f`
argument pointing to the configuration file.

<div class="termy">

```shell
$ dstack run . -f train.dstack.yml --gpu A100

 RUN            CONFIGURATION     BACKEND  RESOURCES        SPOT  PRICE
 wet-mangust-7  train.dstack.yml  aws      5xCPUs, 15987MB  yes   $0.0547  

Provisioning...
---> 100%

TensorBoard 2.14.0 at http://127.0.0.1:6006/

Epoch 0:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
Epoch 1:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
Epoch 2:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
```

</div>

If the `-f` argument is not specified, `dstack` looks for the default configuration (`.dstack.yml`) in the working directory.

#### Request resources

The `dstack run` command allows you to use `--gpu` to request GPUs (e.g. `--gpu A100` or `--gpu 80GB` or `--gpu A100:4`, etc.),
`--memory` to request memory (e.g. `--memory 128GB`),
and many other options (incl. spot instances, max price, max duration, retry policy, etc.).

For more details on the `dstack run` command, refer to the [Reference](reference/cli/run.md).

## Using API

As an alternative to the CLI, you can run tasks and services and manage runs programmatically.

### Create a client

First, create an instance of `dstack.api.Client`:

```python
from dstack.api import Client, ClientError

try:
    client = Client.from_config(repo_dir=".")
except ClientError:
    print("Can't connect to the server")
```

The `repo_dir` argument should point to the directory containing the files you want to reference in the task or service
you're running.

### Submit a run

Here's an example of how to run a task:

```python
from dstack.api import Task, Resources, GPU

task = Task(
    image="ghcr.io/huggingface/text-generation-inference:latest",
    env={"MODEL_ID": "TheBloke/Llama-2-13B-chat-GPTQ"},
    commands=[
        "text-generation-launcher --trust-remote-code --quantize gptq",
    ],
    ports=["80"],
)

run = client.runs.submit(
    run_name="my-awesome-run",
    configuration=task,
    resources=Resources(gpu=GPU(memory="24GB")),
)
```

To forward the configured ports to `localhost`, use the `attach` and `detach` methods on the run.

```python
try:
    run.attach()
    
    # ...
except KeyboardInterrupt:
    run.stop(abort=True)
finally:
    run.detach()
```

You can override the local port, for instance, by replacing `"80"` with `"8080:80"`. This will forward port `80`
to `localhost:8080`.

[//]: # (The `stop` method on the run stops the run.)

For more details on the API, make sure to check the [Reference](reference/api/python/index.md).

[//]: # (## What's next?)
[//]: # (TODO: Guides, examples, reference, Discord, etc)