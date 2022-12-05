# Examples

## Hello, world!

Let's start from the very beginning: a workflow that prints `"Hello, world"`.  

Go ahead, and create the `.dstack/workflows/hello.yaml` file in your project directory:

```yaml
workflows:
  - name: hello
    provider: bash
    commands:
      - echo "Hello, world!"
```

Now, use the `dstack run` command to run it:

```shell
dstack run hello
```

You'll see the output in real-time as your workflow is running:

```shell
RUN           WORKFLOW  SUBMITTED  OWNER           STATUS     TAG 
slim-shady-1  hello     now        peterschmidt85  Submitted  
 
Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Hello, world!
```

## Python

The [`bash`](../reference/providers/index.md#bash), [`code`](../reference/providers/index.md#code), 
[`lab`](../reference/providers/index.md#lab), and [`notebook`](../reference/providers/index.md#notebook) providers
come with Python and Conda pre-installed.

Inside the `.dstack/workflows/hello.yaml` file, define the following workflow:

```yaml
workflows:
  - name: hello-py
    provider: bash
    commands:
      - python hello.py
```

Then, create the `hello.py` Python script:

```python
print("Hello, world!")
```


Now, use the `dstack run` command to run it:

```shell
dstack run hello-py
```

You'll see the output in real-time as your workflow is running:

```shell
RUN           WORKFLOW  SUBMITTED  OWNER           STATUS     TAG 
slim-shady-1  hello     now        peterschmidt85  Submitted  
 
Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Hello, world
```

### Python packages

You can use both `pip` and `conda` within workflows install Python packages:

```yaml
workflows:
  - name: hello-pandas
    provider: bash
    commands:
      - pip install pandas
      - python hello_pandas.py
```

### Conda environments

In your workflows, you can create custom Conda environments via `conda env create`, 
save them as artifact, and reuse later from other workflows via `conda activate`.

```yaml
workflows:
  - name: setup-conda
    help: Prepares an environment
    provider: bash
    commands:
      - conda env create --file environment.yml
    artifacts:
      - path: /opt/conda/envs/myenv

  - name: use-conda
    provider: bash
    deps:
      - workflow: setup-conda
    commands:
      - conda activate myenv
      - python hello_pandas.py
```

### Python version

By default, the workflow uses the same Python version that you use locally. 
You can override the major Python version using the `python` property.

```yaml
workflows:
  - name: hello-py-39
    provider: bash
    python: 3.9
    commands:
      - python hello.py
```

## Resources

### GPU acceleration

If you request GPU, the provider pre-installs the CUDA driver for you.

Let's create a workflow that uses a Tesla V100 GPU.

```yaml
workflows:
  - name: gpu-v100
    provider: bash
    commands:
      - nvidia-smi
    resources:
      gpu: 
        name: V100
        count: 1
```

If you don't specify the name of GPU, dstack will use the cheapest available GPU (e.g. Tesla K80). 

```yaml
workflows:
  - name: gpu-1
    provider: bash
    commands:
      - nvidia-smi
    resources:
      gpu: 1
```

!!! info "NOTE:"
    If you want to use GPU with your AWS account, make sure the 
    corresponding [service quota](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html) is approved.

### Memory

Here's an example of a workflow that requires 64GB of RAM.

```yaml
workflows:
  - name: gpu-v100
    provider: bash
    commands:
      - free -m
    resources:
      memory: 64GB
```

### Shared memory

!!! info "NOTE:"
    If your workflow is using parallel communicating processes (e.g. dataloaders in PyTorch), 
    you may need to configure the size of the shared memory (`/dev/shm` filesystem) via the `shm_size` property.

Here's a workflow that uses `16GB` of shared memory.

```yaml
workflows:
  - name: shm-size
    provider: bash
    commands:
      - df /dev/shm
    resources:
      shm_size: 16GB 
```

### Interruptible instances

Interruptible instances (also known as spot instances or preemptive instances) are 
not guaranteed and may be interrupted by the cloud provider at any time.
Because of that, they are typically several times cheaper.

Interruptible instances can be a great way to use expensive GPU at affordable prices.

Here's an example of a workflow that uses an interruptible instance:

```yaml
workflows:
  - name: hello-i
    provider: bash
    commands:
      - echo "Hello world"
    resources:
      interruptible: true
```

!!! info "NOTE:"
    If you want to use interruptible instances with your AWS account, make sure the 
    corresponding [service quota](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html) is approved.

### Run locally

If you want, you can run workflows on your local machine instead of the cloud.
This is helpful if you want to quickly test something locally before spinning resources in the cloud.

Here's an example of how to define such a workflow:

```yaml
workflows:
  - name: hello
    provider: bash
    commands:
      - echo "Hello world"
    resources:
      local: true
```

!!! warning "NOTE:"
    Running workflows locally requires Docker or [NVIDIA Docker](https://github.com/NVIDIA/nvidia-docker) 
    to be installed locally.

### Override resources via CLI

Resources can be configured not only through the YAML file but
also via the `dstack run` command.

The following command that runs the `hello` workflow using interruptible instances with 4 GPUs:

```shell
dstack run hello --gpu 4 -i
```

!!! info "NOTE:"
    To see all supported arguments (that can be used to override resources), 
    use the `dstack run WORKFLOW --help` command.

## Artifacts

Here's a workflow that creates the `output/hello.txt` file and saves it as an artifact.

```yaml
workflows:
  - name: hello-txt
    provider: bash
    commands:
      - echo "Hello world" > output/hello.txt
    artifacts:
      - path: ./output 
```

!!! info "NOTE:"
    Artifacts are saved at the end of the workflow.
    They are not saved if the workflow was aborted (e.g. via `dstack stop -x`).

### Access artifacts

To see artifacts of a run, you can use the
[`dstack artifacts list`](../reference/cli/index.md#dstack-artifacts-list) command followed
by the name of the run.

```shell
dstack artifacts list grumpy-zebra-1
```

It will list all saved files inside artifacts along with their size:

```shell
PATH  FILE                                  SIZE
data  MNIST/raw/t10k-images-idx3-ubyte      7.5MiB
      MNIST/raw/t10k-images-idx3-ubyte.gz   1.6MiB
      MNIST/raw/t10k-labels-idx1-ubyte      9.8KiB
      MNIST/raw/t10k-labels-idx1-ubyte.gz   4.4KiB
      MNIST/raw/train-images-idx3-ubyte     44.9MiB
      MNIST/raw/train-images-idx3-ubyte.gz  9.5MiB
      MNIST/raw/train-labels-idx1-ubyte     58.6KiB
      MNIST/raw/train-labels-idx1-ubyte.gz  28.2KiB
```

To download artifacts, use the [`dstack artifacts download`](../reference/cli/index.md#dstack-artifacts-download) command:

```shell
dstack artifacts download grumpy-zebra-1 .
```

### Mount artifacts

If you want your workflow to save artifacts as you write files to the disk (in real time), 
you can use the `mount` option:

```yaml
workflows:
  - name: hello-sh
    provider: bash
    commands:
      - bash hello.sh
    artifacts:
      - path: ./output
        mount: true
```

!!! info "NOTE:"
    Every read or write operation within the mounted artifact directory will create
    an HTTP request to the cloud storage.

    The `mount` option can be used to save and restore checkpoint files
    if the workflow uses interruptible instances.

## Deps

Deps allow workflows to reuse artifacts via tags or from other workflows.

### Tags

The easiest way to create a tag is to add a tag to a finished run. 

For example, you ran the [`hello-txt`](#artifacts) workflow, and want to use its artifacts in another workflow.

Once the [`hello-txt`](#artifacts) workflow is finished, you can add a tag to it:

```shell
dstack tags add txt-file grumpy-zebra-2
```

The `txt-file` here is the name of the tag, and `grumpy-zebra-2` is the run name of the [`hello-txt`](#artifacts) workflow. 

Now you can use this tag from another workflow:

```yaml
workflows:
  - name: cat-txt
    provider: bash
    deps:
      - tag: txt-file
    commands:
      - cat output/hello.txt
```

!!! tip "NOTE:"
    One more way to create a tag is by uploading local files as tag artifacts. 
    See the [`dstack tags add`](../reference/cli/index.md#dstack-tags-add) command documentation to know more.

### Workflows

Another way to reuse artifacts of a workflow is via the name of the workflow.
This way, dstack will use artifacts of the last run with that name.

Here's a a workflow that uses artifacts of the last run of the `hello-txt` workflow.

```yaml
workflows:
  - name: cat-txt
    provider: bash
    deps:
      - workflow: hello-txt
    commands:
      - cat output/hello.txt
```

!!! info "NOTE:"
    There should be at least one run of the `hello-txt` workflow in the `DONE` status.

### External repos

By default, dstack looks up tags and workflows within the current Git repo only.

If you want to refer to a tag or a workflow from another Git repo, 
you have to prepend the name (of the tag or the workflow) with the repo name.

Here's a workflow that refers to a tag from the `dstackai/dstack` Git repo.

```yaml
workflows:
  - name: cat-txt
    provider: bash
    deps:
      - tag: dstackai/dstack/txt-file
    commands:
      - cat output/hello.txt
```

## Environment variables

You can configure environment variables for workflows using the `env` property. 

Here's a workflow that sets `DSTACK_ENV_1`, `DSTACK_ENV_2`, and `DSTACK_ENV_3` environment variables:

```yaml
workflows:
  - name: hello-env
    provider: bash
    env:
      - DSTACK_ENV_1=VAL1
      - DSTACK_ENV_2=VAL2
      - DSTACK_ENV_3
    commands:
      - env | grep DSTACK_
```

## Args

Workflows can be parametrized. 

When you pass any parameters to the `dstack run` command, they can be accessed from the workflow YAML file via
the `${{ run.args }}` expression. 

Here's an example:

```yaml
workflows:
  - name: hello-args
    provider: bash
    commands:
      - python hello-arg.py ${{ run.args }}
```

If you run the following command:

```shell
dstack run hello-arg "Hello, world!"
```

It will pass the `"Hello, world!"` argument to the `hello-arg.py` script.

!!! info "NOTE:"
    You can use any arguments except those that are reserved for the [`dstack run`](../reference/cli/index.md#dstack-run) command.

## Apps

The [`bash`](../reference/providers/index.md#bash) and [`docker`](../reference/providers/index.md#docker) providers 
allow workflows to host applications.

To do that, you have to pass the number of ports (that you want to expose) to the `ports` property.

Here's a workflow that launches a FastAPI application.

```yaml
workflows:
  - name: hello-fastapi
    provider: bash
    ports: 1
    commands:
      - pip install fastapi uvicorn
      - uvicorn hello_fastapi:app --port $PORT_0 --host 0.0.0.0
```

```python
   from fastapi import FastAPI
   
   app = FastAPI()
   
   
   @app.get("/")
   async def root():
       return {"message": "Hello World"}
```

!!! info "NOTE:"
    The actual port numbers will be passes to the workflow via environment variables `PORT_0`, `PORT_1`, 
    etc.
    
    Don't forget to use `0.0.0.0` as the hostname.

## Secrets

Secrets can be used to access passwords and tokens securely from workflows (without hard-coding them in the code).

### Weights & Biases

Here's an example of how to use your Weight & Biases API token in your workflows. 

Go to the settings of your Weight & Biases user and copy your API token. 

Use the `dstack secrets add` command to add it as a secret:

```shell
dstack secrets add WANDB_API_KEY acd0a9e1ebe7a4e4854d2f6a7cef85b5257f8183
```

Now, when you run any workflow, your API token will be passed to the workflow 
via the `WANDB_API_KEY` environment variable:

```yaml
workflows:
  - name: hello
    provider: bash
    commands:
      - pip install wandb
      - wandb login
```

Secrets can be managed via the [`dstack secrets`](../reference/cli/index.md#dstack-secrets-add) command.

## Dev environments

Dev environments is a great way to run code interactively using an IDE, a notebook, or a terminal.

### VS Code

This workflow launches a VS Code dev environment.

```yaml
workflows:
  - name: ide
    provider: code
```

Here's an example if you need 1 GPU and 64GB of RAM.

```yaml
workflows:
  - name: ide-v80
    provider: code
    resources:
      memory: 64GB
      gpu: 1
```

### JupyterLab and Jupyter

You can launch JupyterLab and Jupyter dev environments the very same way – just 
replace `code` with `lab` or `notebook`.