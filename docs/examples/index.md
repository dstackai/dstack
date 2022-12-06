# Examples

!!! tip "NOTE:"
    All examples can be found on [GitHub](https://github.com/dstackai/dstack-examples).
    Feel free to [install `dstack`](../installation.md), clone the [repo](https://github.com/dstackai/dstack-examples), 
    and follow the instructions.

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

Run it locally using the `dstack run --local` command:

```shell hl_lines="1"
dstack run hello --local
```

You'll see the output in real-time as your workflow is running:

```shell hl_lines="1"
RUN           WORKFLOW  SUBMITTED  OWNER           STATUS     TAG 
slim-shady-1  hello     now        peterschmidt85  Submitted  
 
Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Hello, world!
```

## Python

!!! info "NOTE:"
    The [`bash`](../reference/providers/index.md#bash), [`code`](../reference/providers/index.md#code), 
    [`lab`](../reference/providers/index.md#lab), and [`notebook`](../reference/providers/index.md#notebook) providers
    come with Python and Conda pre-installed.

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

Run it locally using the `dstack run --local` command:

```shell hl_lines="1"
dstack run hello-py --local 
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

Run it locally using the `dstack run --local` command:

```shell hl_lines="1"
dstack run hello-pandas --local
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

First, run the `setup-conda` workflow locally:

```shell hl_lines="1"
dstack run setup-conda --local
```

And then, run the `use-conda` workflow locally:

```shell hl_lines="1"
dstack run use-conda --local
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

Run it locally using the `dstack run --local` command:

```shell hl_lines="1"
dstack run python-version --local
```

## Resources

If you're not explicitly telling `dstack` to run the workflow locally, `dstack`
runs it in the configured cloud account, and provisions the resources
described in the `resources` property of the workflow YAML file. 

### GPU acceleration

The workflow below will automatically create a machine with one `NVIDIA Tesla V100` GPU:

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

Run it using the `dstack run` command:

```shell hl_lines="1"
dstack run gpu-v100
```

!!! info "NOTE:"
    If you want to use GPU with your AWS account, make sure to have the 
    corresponding [service quota](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html) approved
    by the AWS support team beforehand.
    The approval typically takes a few business days.

### Memory

The workflow below provisions a machine with 64GB memory:

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

Run it using the `dstack run` command:

```shell hl_lines="1"
dstack run mem-64gb
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

Run it using the `dstack run` command:

```shell hl_lines="1"
dstack run shm-size
```

### Interruptible instances

Interruptible instances (also known as spot instances or preemptive instances) are 
offered at a significant price discount, and allow to use expensive machines at affordable prices.

The workflow below uses an interruptible instance with one default GPU (`NVIDIA Tesla K80`):

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

### Run locally

To run a workflow locally, you have to either set `local` to `true` inside the `resources` property,
or pass `--local` directly to the `dstack run`.

This workflow will run locally by default:

=== "`.dstack/workflows/resources.yaml`"

    ```yaml
    workflows:
      - name: local-hello
        provider: bash
        commands:
          - echo "Hello world"
        resources:
          local: true
    ```

You don't have to use `--local` with `dstack run`:

```shell hl_lines="1"
dstack run local-hello
```

!!! warning "NOTE:"
    Running workflows locally requires Docker or [NVIDIA Docker](https://github.com/NVIDIA/nvidia-docker) 
    to be installed locally.

### Override resources via CLI

Resources can be configured not only through the YAML file but
also via the `dstack run` command.

The following command that runs the `hello` workflow using interruptible instances with four GPUs:

```shell hl_lines="1"
dstack run hello --gpu 4 -i
```

!!! info "NOTE:"
    To see all supported arguments (that can be used to override resources), 
    use the `dstack run WORKFLOW --help` command.

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

Run it locally using `dstack run --local`:

```shell hl_lines="1"
dstack run hello-txt
```

!!! info "NOTE:"
    Artifacts are saved at the end of the workflow.
    They are not saved if the workflow was aborted (e.g. via `dstack stop -x`).

### Access artifacts

To see artifacts of a run, you can use the
[`dstack artifacts list`](../reference/cli/index.md#dstack-artifacts-list) command followed
by the name of the run.

```shell hl_lines="1"
dstack artifacts list grumpy-zebra-1
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

To download artifacts, use the [`dstack artifacts download`](../reference/cli/index.md#dstack-artifacts-download) command:

```shell hl_lines="1"
dstack artifacts download grumpy-zebra-1 .
```

### Real-time artifacts

If you want your workflow to save artifacts in real time (as you write files to the disk), 
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

Run it using the `dstack run` command:

```shell
dstack run hello-sh
```

!!! info "NOTE:"
    Every read or write operation within the mounted artifact directory will create
    an HTTP request to the storage.

    The `mount` option can be used to save and restore checkpoint files
    if the workflow uses interruptible instances.

## Deps

Deps allow workflows to reuse artifacts from tags or from other workflows.

### Tags

Tags can be managed using the `dstack tags` command.

You can create a tag either by uploading any data and specifying a tag name,
or by assigning a tag name to a finished run.

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

!!! tip "NOTE:"
    If you want to create a tag buy uploading data from your local machine, 
    use the [`dstack tags add`](../reference/cli/index.md#dstack-tags-add) command with `-a PATH` argument pointing to
    the local folder with the data to upload.

### Workflows

Another way to reuse artifacts of a workflow is by using the name of a workflow.

The workflow below uses the output artifacts from the last run of the `hello-txt` workflow:

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

### External repos

By default, dstack looks up tags and workflows within the same Git repo.

If you want to refer to a tag or a workflow from another Git repo, 
you have to prepend the name (of the tag or the workflow) with the repo name.

The workflow below uses a tag from the `dstackai/dstack` Git repo.

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
    Make sure to run the `hello-txt` workflow inside the `dstackai/dstack` repo beforehand.

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

Secrets can be used to access passwords and tokens securely from workflows (without hard-coding them in the code).

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