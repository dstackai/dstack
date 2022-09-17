# Examples

!!! info "NOTE:"
    If you use the `bash`, `code`, `lab`, or `notebook` provider, the workflow environment
    is pre-configured with the correct version of CUDA driver, Conda, and Python.

    You can run the dstack CLI only from inside a Git repository directory.

    All your project files that you want to use in the workflow must be under Git: if not committed, then at least staged
    via `git add`.

Find below different workflow examples.

## Hello world

This workflow prints `"Hello world"` to the output.

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: hello
        provider: bash
        commands:
          - echo "Hello world"
    ```

## Python

This workflow runs a Python script.

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: hello-py
        provider: bash
        commands:
          - python hello.py
    ```

=== "hello.py"

    ```python
    print("Hello world")
    ```

By default, it uses the Python version `3.10`. If you want, you can set the major version of Python
that needs to be pre-installed using the `python` property:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: hello-py-39
        provider: bash
        python: 3.9
        commands:
          - python hello.py
    ```

=== "hello.py"

    ```python
    print("Hello world")
    ```

Because the provider, pre-installed and activated Conda, you can use the `conda` executable to install Python packages:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: hello-pandas
        provider: bash
        commands:
          - conda install pandas -y
          - python hello_pandas.py
    ```

=== "hello_pandas.py"

    ```python
    import pandas as pd

    data = {
      "calories": [420, 380, 390],
      "duration": [50, 40, 45]
    }
    
    #load data into a DataFrame object:
    df = pd.DataFrame(data)
    
    print(df) 
    ```

## Resources

If you use the `bash`, `code`, `lab`, or `notebook` provider, you can specify the hardware requirements
for the workflow using the `resources` property.

For example, you can tell how much memory the workflow needs, how many CPUs,
how many GPU and of what type, and also whether you want to use standard instances or
interruptible instances (also known as spot or preemptive instances).

#### GPU

This workflow is using 1 GPU:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: gpu-1
        provider: code
        commands:
          - nvidia-smi
        resources:
          gpu: 
            count: 1
    ```

!!! info "NOTE:"
    By default, before you can use GPU instances with your AWS account, the 
    corresponding [service quota](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html) has to 
    requested and approved.

#### Memory and name of GPU

This workflow is using 64GB of memory and 1 Tesla V100 GPU:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: gpu-v100
        provider: code
        commands:
          - nvidia-smi
        resources:
          memory: 64GB
          gpu:
            name: V100
            count: 1
    ```

!!! info "NOTE:"
    By default, dstack picks the most cheap instance that matches the requirements.

    It's important to understand that the `resources` property defines the minimum requirements.
    In fact, the instance may have more resources (incl. memory, CPU, and GPU).

    For AWS, dstack uses M, C, and P instances only. 

#### Interruptible instance with GPU

This workflow is using an interruptible instance with 1 GPU:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: gpu-i
        provider: code
        commands:
          - nvidia-smi
        resources:
          interruptible: true
          gpu: 
            count: 1
    ```

!!! info "NOTE:"
    By default, before you can use spot instances with your AWS account, the 
    corresponding [service quota](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html) has to 
    requested and approved. 

#### Shared memory

If your workflow is using parallel processes that communicate with each other through shared memory
(/dev/shm, e.g. dataloaders in PyTorch), you may need to configure the size of the shared memory
via the `shm_size` property.

This workflow is using `16GB` of shared memory:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: shm-size
        provider: code
        commands:
          - df /dev/shm
        resources:
          shm_size: 16GB 
    ```

## Dev environments

#### VS Code

This workflow launches a VS Code dev environment.

You have to use the `code` provider.

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: ide
        provider: code
    ```

Once the workflow is started, you'll see the link to open the VS Code application in the logs.

This provider is very convenient when you want to interactively work with your code using
a code editor and a terminal.

Once you don't need the dev environment, you can stop the workflow.

Just like with other providers, you can configure [resources](../workflows/code.md#resources) for your dev environment, 
use the `resources` property:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: ide-v80
        provider: code
        resources:
          memory: 64GB
          gpu: 
            name: V80
            count: 1
    ```

!!! info "NOTE:"
    Similar to other providers, the `code` provider allows you to use the `deps` and `artifacts` too, e.g.
    in case you may want to automatically pre-download the artifacts from dependencies,
    or store output artifacts for later use.

#### JupyterLab and Notebook

The `lab` and `notebook` providers work absolutely the same way as the `code` provider. Feel free to use the
examples from above and just replace the `code` with `lab` or `notebook`.

## Artifacts

This workflow creates a `output/hello.txt` file with `"Hello world"` inside and saves it as an output artifact.

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: hello-txt
        provider: bash
        commands:
          - echo "Hello world" > output/hello.txt
        artifacts:
          - path: output 
    ```

!!! info "NOTE:"
    By default, artifacts are saved at the end of the workflow.
    Artifacts are saved even if you stop the workflow with `dstack stop`.
    Artifacts are not saved if you abort the workflow, e.g. with `dstack stop -x`. 

#### Mount artifacts

In case you'd like an artifact to be saved in real-time as you write to the disk,
you can set the `mount` property of the artifact to `true`.

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: hello-sh
        provider: bash
        commands:
          - bash hello.sh
        artifacts:
          - path: output
            mount: true
    ```

=== "hello.sh"

    ```bash
    for i in {000..100}
    do
        sleep 1
        echo $i > "output/${i}.txt"
        echo "Wrote output/${i}.txt"
    done
    ```

!!! warning "NOTE:"
    Must be used only when real-time access to the artifacts is important. 
    For example, for storing checkpoints when interruptible instances are used, or for storing
    event files in real-time (e.g. TensorBoard event files.)
    By default, it's `false`.

## Deps

#### Tags

Before tags can be used in workflows, they must be added.

For example, you ran the `hello-txt` workflow (from above) and want to use its output artifacts
from other workflows.

Let's create the tag `txt-file`. Make sure to pass there the name of the run of a finished `hello-txt` workflow.

```shell
dstack tags add txt-file <run-name>
```

Now you can use your tag from other workflow:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: cat-txt
        provider: bash
        deps:
          - tag: txt-file
        commands:
          - cat output/hello.txt
    ```

#### Workflows

If you want to use the output artifacts of one workflow from another one, and don't want to create a tag,
you can specify a dependency by a name of the workflow.

This workflow uses the output artifacts of the recent `hello-txt` workflow.

=== ".dstack/workflows.yaml"

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
    There should be at least one workflow of the specified name with the status `Done`.
    Use `dstack ps -a` to see all the recent workflows.

#### Environment variables

This workflow defines environment variables and prints them to the output. It uses the `env` bash command
to print current environment variables. 

=== ".dstack/workflows.yaml"

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

#### Ports

Both the `bash` and `docker` providers allow to open ports.

To do that, you have to use the `ports` property to specify the number of needed ports.

WHen the workflow starts, the exact port numbers will be provided as environment variables `PORT_0`, `PORT_1`, 
...

Make sure to use the `0.0.0.0` as the hostname so the port is bound correctly.

dstack will automatically replace the URL printed by the FastAPI to the output with the correct URL
of the running application.

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: hello-fastapi
        provider: bash
        ports: 1
        commands:
          - pip install fastapi uvicorn
          - uvicorn hello_fastapi:app --port $PORT_0 --host 0.0.0.0
    ```

=== "hello_fastapi.py"

    ```python
       from fastapi import FastAPI
       
       app = FastAPI()
       
       
       @app.get("/")
       async def root():
           return {"message": "Hello World"}
    ```

## Docker

Sometimes you may want to run workflows using your own custom Docker image.

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
       - name: hello-docker
         provider: docker
         image: hello-world
    ```

If you want, you can specify your own commands:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: hello-docker-2
        provider: docker
        image: ubuntu
        commands:
          - echo "Hello world"
    ```

!!! info "NOTE:"
    Just like with other providers, the `docker` provider also supports the `deps`, `artifacts`, `resources`,
    and `ports` properties.

    Unlike the `bash`, `code`, `lab`, and `notebook` providers, the `docker` provider doesn't have 
    the CUDA driver and Conda pre-installed.

    If you want, you can use the [`dstackai/miniconda`](https://hub.docker.com/repository/docker/dstackai/miniconda) 
    base Docker image that has the CUDA driver and Conda pre-installed.