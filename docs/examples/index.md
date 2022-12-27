# Examples

This section of the documentation showcases the main capabilities of `dstack`. The source code for the examples can 
be found on [GitHub](https://github.com/dstackai/dstack-examples).

## Hello, world!

The workflow below prints `"Hello, world"`.

=== "`.dstack/workflows/hello.yaml`"

    ```yaml
    workflows:
      - name: hello
        provider: bash
        commands:
          - echo "Hello, world!"
    ```

### Run locally

To run a workflow locally, simply use the `dstack run` command:

```shell hl_lines="1"
dstack run hello
```

You'll see the output in real-time:

```shell hl_lines="1"
RUN           WORKFLOW  SUBMITTED  OWNER           STATUS     TAG 
slim-shady-1  hello     now        peterschmidt85  Submitted  
 
Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Hello, world!
```

!!! warning "NOTE:"
    To run workflows locally, it is required to have either Docker or [NVIDIA Docker](https://github.com/NVIDIA/nvidia-docker) 
    pre-installed.

### Run remotely

To run a workflow remotely, add the `--remote` flag (or `-r`) to 
the `dstack run` command:

```shell hl_lines="1"
dstack run hello --remote
```

This will automatically set up the necessary infrastructure (e.g. within a 
configured cloud account), run the workflow, and upon completion, tear down 
the infrastructure.

```shell hl_lines="1"
RUN           WORKFLOW  SUBMITTED  OWNER           STATUS     TAG 
slim-shady-1  hello     now        peterschmidt85  Submitted  
 
Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Hello, world!
```

!!! info "NOTE:"
    You can use `pip`, `conda`, and `python` executables from the `commands` property of your workflow.
    See [Python](#python) for more details.

## Artifacts

The workflow below creates the `output/hello.txt` file and saves it as an artifact:

=== "`.dstack/workflows/artifacts.yaml`"

    ```yaml
    workflows:
      - name: hello-txt
        provider: bash
        commands:
          - echo "Hello world" > output/hello.txt
        artifacts:
          - path: ./output
    ```

Run it locally using `dstack run`:

```shell hl_lines="1"
dstack run hello-txt
```

!!! info "NOTE:"
    Artifacts are saved at the end of the workflow.
    They are not saved if the workflow was aborted (e.g. via `dstack stop -x`).

### List artifacts

To see artifacts of a run, you can use the
[`dstack ls`](../reference/cli/index.md#dstack-artifacts-list) command followed
by the name of the run.

```shell hl_lines="1"
dstack ls grumpy-zebra-1
```

It will list all saved files inside artifacts along with their size:

```shell hl_lines="1"
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

### Push artifacts to the cloud

When you run a workflow locally, artifacts are stored in `~/.dstack/artifacts` and can be reused only from the workflows
that run locally too.

If you'd like to reuse the artifacts outside your machine, you must push these artifacts using the `dstack push` command:

```shell hl_lines="1"
dstack push grumpy-zebra-1
```

!!! info "NOTE:"
    If you run a workflow remotely, artifacts are pushed automatically, and it's typically a lot faster
    than pushing artifacts of a local run.

### Real-time artifacts

If you run your workflow remotely, and want to save artifacts in real time (as you write files to the disk), 
you can set the `mount` property to `true` for a particular artifact.

The workflow below creates files in `output` and save them as artifacts in real-time:

=== "`.dstack/workflows/resources.yaml`"

    ```yaml
    workflows:
      - name: hello-sh
        provider: bash
        commands:
          - bash artifacts/hello.sh
        artifacts:
          - path: ./output
            mount: true
    ```

=== "`artifacts/hello.sh`"

    ```shell
    for i in {000..100}
    do
        sleep 1
        echo $i > "output/${i}.txt"
        echo "Wrote output/${i}.txt"
    done
    ```

Go ahead and run this workflow remotely:

```shell
dstack run hello-sh --remote
```

!!! info "NOTE:"
    Every read or write operation within the mounted artifact directory will create
    an HTTP request to the storage.

    The `mount` option can be used to save and restore checkpoint files
    if the workflow uses interruptible instances.

## Deps

Using deps, workflows can reuse artifacts from other workflows. There are two methods for doing this: by specifying a
tag name or a workflow name

### Workflows

The workflow below uses the output artifacts of the most recent run of the `hello-txt` workflow:

=== "`.dstack/workflows/deps.yaml`"

    ```yaml
    workflows:
      - name: cat-txt-2
        provider: bash
        deps:
          - workflow: hello-txt
        commands:
          - cat output/hello.txt
    ```

!!! info "NOTE:"
    Make sure to run the `hello-txt` workflow beforehand.

### Tags

Tags can be managed using the `dstack tags` command.

You can create a tag either by assigning a tag name to a finished run or by uploading any local data.

Say, you ran the [`hello-txt`](#artifacts) workflow, and want to reuse its artifacts in another workflow.

Once the [`hello-txt`](#artifacts) workflow is finished, you can add a tag to it:

```shell hl_lines="1"
dstack tags add txt-file grumpy-zebra-2
```

The `txt-file` here is the name of the tag, and `grumpy-zebra-2` is the run name of the 
[`hello-txt`](#artifacts) workflow. 

Let's reuse the `txt-file` tag from another workflow:

=== "`.dstack/workflows/deps.yaml`"

    ```yaml
    workflows:
      - name: cat-txt
        provider: bash
        deps:
          - tag: txt-file
        commands:
          - cat output/hello.txt
    ```

!!! info "NOTE:"
    Tags are only supported for remote runs. If you want to use a tag for a local run, you must first push the 
    artifacts of the local run using the `dstack push` command. 

    You can create also a tag by uploading arbitrary local files. To do this, use the `dstack tags add` command 
    with the `-a PATH` argument, which should point to the local folder containing local files.

### External repos

By default, dstack looks up tags and workflows within the same repo.

If you want to refer to a tag or a workflow from another repo, 
you have to prepend the name (of the tag or the workflow) with the repo name.

The workflow below uses a tag from the `dstackai/dstack` repo:

=== "`.dstack/workflows/deps.yaml`"

    ```yaml
    workflows:
      - name: cat-txt-3
        provider: bash
        deps:
          - workflow: dstackai/dstack/txt-file
        commands:
          - cat output/hello.txt
    ```

!!! info "NOTE:"
    Make sure to run the `hello-txt` workflow in the `dstackai/dstack` repo beforehand.

## Resources

By default, `dstack` runs workflows locally and utilizes the resources available on your machine.

When you run the workflow in remotely, you can use the `resources` property in your YAML file to specify which 
resources are required by the workflow.

### GPU acceleration

If you run the following workflow remotely, `dstack` will automatically provision a machine with one 
`NVIDIA Tesla V100` GPU:

=== "`.dstack/workflows/resources.yaml`"

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

Go ahead, and run this workflow remotely:

```shell hl_lines="1"
dstack run gpu-v100 --remote
```

!!! info "NOTE:"
    If you want to use GPU with your AWS account, make sure to have the 
    corresponding [service quota](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html) approved
    by the AWS support team beforehand.
    The approval typically takes a few business days.

### Memory

If you run the following workflow remotely, `dstack` will automatically provision a machine with 64GB memory:

=== "`.dstack/workflows/resources.yaml`"

    ```yaml
    workflows:
      - name: mem-64gb
        provider: bash
        commands:
          - free --giga
        resources:
          memory: 64GB
    ```

Go ahead, and run this workflow remotely:

```shell hl_lines="1"
dstack run mem-64gb --remote
```

### Shared memory

If your workflow is using parallel communicating processes (e.g. dataloaders in PyTorch), 
you may need to configure the size of the shared memory (`/dev/shm` filesystem) via the `shm_size` property.

The workflow below uses `16GB` of shared memory:

=== "`.dstack/workflows/resources.yaml`"

    ```yaml
    workflows:
      - name: shm-size
        provider: bash
        commands:
          - df /dev/shm
        resources:
          shm_size: 16GB 
    ```

Try running this workflow either locally or remotely

```shell hl_lines="1"
dstack run shm-size
```

### Interruptible instances

Interruptible instances (also known as spot instances or preemptive instances) are 
offered at a significant price discount, and allow to use expensive machines at affordable prices.

If you run the following workflow remotely, `dstack` will automatically provision a spot instance with one default GPU 
(`NVIDIA Tesla K80`):

=== "`.dstack/workflows/resources.yaml`"

    ```yaml
    workflows:
      - name: gpu-i
        provider: bash
        commands:
          - nvidia-smi
        resources:
          interruptible: true
          gpu: 1
    ```

!!! info "NOTE:"
    If you want to use interruptible instances with your AWS account, make sure to have the 
    corresponding [service quota](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html) approved
    by the AWS support team beforehand.
    The approval typically takes a few business days.

### Run remotely by default

If you plan to run a workflow remotely by default (and don't want to include the `--remote` flag to the `dstack run` command
each time), you can set `remote` to `true` inside `resources`.

This workflow will run remotely by default:

=== "`.dstack/workflows/resources.yaml`"

    ```yaml
    workflows:
      - name: local-hello
        provider: bash
        commands:
          - echo "Hello world"
        resources:
          remote: true
    ```

Go ahead and run it with `dstack run`:

```shell hl_lines="1"
dstack run local-hello
```

### Override resources via CLI

Resources can be configured not only through the YAML file but
also via the `dstack run` command.

The following command that runs the `hello` workflow remotely using a spot instance with four GPUs:

```shell hl_lines="1"
dstack run hello --remote --gpu 4 --interruptible
```

!!! info "NOTE:"
    To see all supported arguments (that can be used to override resources), 
    use the `dstack run WORKFLOW --help` command.

## Dev environments

For debugging purposes, you can attach dev environments to your workflows, and run code interactively.

This is especially useful when you're just designing your workflow.

### VS Code

The workflow below launches a VS Code dev environment:

=== "`.dstack/workflows/dev-environments.yaml`"

    ```yaml
    workflows:
      - name: ide-code
        provider: code
    ```

Run it locally using the `dstack run --local` command:

```shell hl_lines="1"
dstack run ide-code --local
```

Once you run it, you'll see the URL to open VS Code in the output:

```shell hl_lines="1"
 RUN               WORKFLOW  SUBMITTED  OWNER           STATUS     TAG
 light-lionfish-1  ide-code  now        peterschmidt85  Submitted

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Web UI available at http://127.0.0.1:51303/?folder=%2Fworkflow&tkn=f2de121b04054f1b85bb7c62b98f2de1
```

Below is a workflow that launches a VS Code but uses one default GPU and 64GB of memory:

=== "`.dstack/workflows/dev-environments.yaml`"

    ```yaml
    workflows:
      - name: ide-code-gpu
        provider: code
        resources:
          memory: 64GB
          gpu: 1
    ```

Run it using the `dstack run` command:

```shell hl_lines="1"
dstack run ide-code-gpu
```

### JupyterLab and Jupyter

You can launch JupyterLab and Jupyter dev environments the very same way, Just replace the `code` provider 
name with `lab` or `notebook`.

## Environment variables

The workflow below sets environment variables:

=== "`.dstack/workflows/envs.yaml`"

    ```yaml
    workflows:
      - name: hello-env
        provider: bash
        env:
          - DSTACK_ENV_1=VAL1
          - DSTACK_ENV_2=VAL2
          - DSTACK_ENV_3
        commands:
          - env
    ```

## Args

Workflows can be parametrized. 

When you pass any parameters to the `dstack run` command, they can be accessed from the workflow YAML file via
the `${{ run.args }}` expression. 

The workflow below passes workflow arguments to `hello-arg.py`:

=== "`.dstack/workflows/args.yaml`"

    ```yaml
    workflows:
      - name: hello-args
        provider: bash
        commands:
          - python args/hello-arg.py ${{ run.args }}
    ```

=== "`args/hello-arg.py`"

    ```python
    import sys

    if __name__ == '__main__':
        print(sys.argv)
    ```

Run it locally using `dstack run --local` and passing `"Hello, world!"` as an argument:

```shell hl_lines="1"
dstack run hello-arg "Hello, world!"
```

!!! info "NOTE:"
    It supports any arguments except those that are reserved for the [`dstack run`](../reference/cli/index.md#dstack-run) command.

## Apps

!!! info "NOTE:"
    Both the [`bash`](../reference/providers/index.md#bash) and [`docker`](../reference/providers/index.md#docker) providers 
    allow workflows to host applications.

To host apps within a workflow, you have to request the number of ports that your apps need. 
Use the `ports` property for that.

The actual port numbers will be passes to the workflow via environment variables `PORT_0`, `PORT_1`, etc.

The workflow below launches a FastAPI application:

=== "`.dstack/workflows/apps.yaml`"

    ```yaml
    workflows:
      - name: hello-fastapi
        provider: bash
        ports: 1
        commands:
          - pip install fastapi uvicorn
          - uvicorn apps.hello_fastapi:app --port $PORT_0 --host 0.0.0.0
    ```

=== "`apps/hello_fastapi.py`"

    ```python
    from fastapi import FastAPI

    app = FastAPI()
    
    
    @app.get("/")
    async def root():
        return {"message": "Hello World"}
    ```

!!! info "NOTE:" 
    Don't forget to bind your application to the `0.0.0.0` hostname.

## Secrets

Secrets can be used to access passwords and tokens securely from remote workflows (without hard-coding them in the code).

### Weights & Biases

Here's an example of how to use your Weight & Biases API token in your workflows. 

Go to the settings of your Weight & Biases user and copy your API token. 

Use the `dstack secrets add` command to add it as a secret:

```shell hl_lines="1"
dstack secrets add WANDB_API_KEY acd0a9d1ebe3a4e4854d2f6a7cef85b5257f8183
```

Now, when you run any workflow, your API token will be passed to the workflow 
via the `WANDB_API_KEY` environment variable:

=== "`.dstack/workflows/secrets.yaml`"

    ```yaml
    workflows:
      - name: hello
        provider: bash
        commands:
          - conda install wandb
          - wandb login
    ```

Secrets can be managed via the [`dstack secrets`](../reference/cli/index.md#dstack-secrets-add) command.

!!! info "NOTE:"
    Secrets are currently only supported by remote workflows.

[//]: # (TODO: Align secrets with local and remote workflows)

## Python

The workflow below runs a Python script that prints `"Hello, world!"`:

=== "`.dstack/workflows/python.yaml`"

    ```yaml
    workflows:
      - name: hello-py
        provider: bash
        commands:
          - python python/hello.py
    ```

=== "`python/hello.py`"

    ```python
    if __name__ == '__main__':
        print("Hello, world!")
    ```

Run it locally using the `dstack run` command:

```shell hl_lines="1"
dstack run hello-py
```

You'll see the output in real-time as your workflow is running:

```shell hl_lines="1"
RUN           WORKFLOW  SUBMITTED  OWNER           STATUS     TAG 
slim-shady-1  hello-py  now        peterschmidt85  Submitted  
 
Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Hello, world
```

### Python packages

You can use both `pip` and `conda` within workflows install Python packages.

The workflow below installs `pandas` via `pip` and runs a Python script that uses `pandas`:

=== "`.dstack/workflows/python.yaml`"

    ```yaml
    workflows:
      - name: hello-pandas
        provider: bash
        commands:
          - pip install pandas
          - python python/hello_pandas.py
    ```

=== "`python/hello_pandas.py`"

    ```python
    import pandas as pd

    if __name__ == '__main__':
        df = pd.DataFrame(
            {
                "Name": [
                    "Braund, Mr. Owen Harris",
                    "Allen, Mr. William Henry",
                    "Bonnell, Miss. Elizabeth",
                ],
                "Age": [22, 35, 58],
                "Sex": ["male", "male", "female"],
            }
        )
    
        print(df)

    ```

Run it locally using the `dstack run` command:

```shell hl_lines="1"
dstack run hello-pandas
```

### Conda environments

You can create your custom Conda environments using `conda env create`, 
save them as artifact, and reuse from other workflows via `deps` and `conda activate`:

=== "`.dstack/workflows/conda.yaml`"

    ```yaml
    workflows:
      - name: setup-conda
        provider: bash
        commands:
          - conda env create --file conda/environment.yaml
        artifacts:
          - path: /opt/conda/envs/myenv
    
      - name: use-conda
        provider: bash
        deps:
          - workflow: setup-conda
        commands:
          - conda activate myenv
          - python conda/hello_pandas.py
    
    ```

=== "`conda/hello_pandas`"

    ```python
    import pandas as pd

    if __name__ == '__main__':
        df = pd.DataFrame(
            {
                "Name": [
                    "Braund, Mr. Owen Harris",
                    "Allen, Mr. William Henry",
                    "Bonnell, Miss. Elizabeth",
                ],
                "Age": [22, 35, 58],
                "Sex": ["male", "male", "female"],
            }
        )
    
        print(df)

    ```

First, run the `setup-conda` workflow:

```shell hl_lines="1"
dstack run setup-conda
```

And then, run the `use-conda` workflow:

```shell hl_lines="1"
dstack run use-conda
```

The `use-conda` workflow will reuse the `myenv` environment from the `setup-conda` workflow.

!!! warning "NOTE:"
    Conda environments are always bound to a specific architecture and cannot be reused on machines 
    that has a different architecture (e.g. `AMD64` vs `ARM64`).

### Python version

By default, the workflow uses the same Python version that you use locally. 
You can override the major Python version using the `python` property:

=== "`.dstack/workflows/python-version.yaml`"

    ```yaml
    workflows:
      - name: python-version
        provider: bash
        python: 3.7
        commands:
          - python --version
    ```

Run it locally using the `dstack run` command:

```shell hl_lines="1"
dstack run python-version
```