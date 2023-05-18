# Pipelines

A pipeline is a set of pre-defined configurations that allow to process data, train or fine-tune models, do batch inference 
or other tasks.

With `dstack`, you can define such configurations as code and run your tasks with a single command, either locally or in
any cloud.

## Creating a configuration file

A configuration can be defined as a YAML file (under the `.dstack/workflows` directory).

<div editor-title=".dstack/workflows/train-pipeline.yaml"> 

```yaml
workflows:
  - name: train-pipeline
    provider: bash
    commands:
      - pip install -r requirements.txt
      - python train.py
    artifacts:
      - ./lightning_logs
    resources:
      gpu:
        name: P100
```

</div>

The [configuration](../reference/providers/bash.md) allows you to customize hardware resources, set up the Python environment, output artifacts, 
expose ports, configure cache, and of course provide the commands to run.

The artifacts are saved at the end of the run, such as when it's stopped or finished.

[//]: # (TODO [MAJOR]: It doesn't allow to save artifacts via Python API)

[//]: # (TODO [MEDIUM]: It doesn't explain how to mount deps)

[//]: # (TODO [MAJOR]: It supports only YAML and doesn't allow to use pure Python)

[//]: # (TODO [MAJOR]: Currently, it doesn't allow to define multiple steps)

## Running a pipeline

Once a configuration is defined, you can run it using the `dstack run` command:

<div class="termy">

```shell
$ dstack run train-pipeline

RUN      WORKFLOW        SUBMITTED  STATUS     TAG
shady-1  train-pipeline  now        Submitted  
 
Provisioning... It may take up to a minute. ✓

GPU available: True, used: True

Epoch 1: [00:03<00:00, 280.17it/s, loss=1.35, v_num=0]
---> 100%
```

</div>

For convenience, `dstack` uses an exact copy of the source code that is locally present in the folder where you use the `dstack` command.

??? info "Using .gitignore"
    If you don't want the pipeline to sync certain files (especially large local files that are not needed
    for the pipeline), feel free to add them to the `.gitignore` file. In this case, `dstack` will ignore them,
    even if you aren't using Git.

If you configure a project to run pipelines in the cloud, `dstack` will automatically provision the required cloud
resources. After the workflow is finished, `dstack` will automatically save output artifacts and clean up cloud resources.

??? info "Configuring projects"
    The default project runs pipelines locally. However, you can
    log into Hub and configure additional projects to run pipelines in a cloud account of your choice. 

    You can configure multiple projects and pass the project name to the CLI by using the `--project` argument.

#### Stopping a run

To stop the run, click `Ctrl`+`C` while the [`dstack run`](../reference/cli/run.md) command is running,
or use the [`dstack stop`](../reference/cli/stop.md) command.

## Configuring hardware resources

If your project is configured to run pipelines in the cloud, you can use the 
[`resources`](../reference/providers/bash.md#resources) property in the YAML file to 
request hardware resources like memory, GPUs, and shared memory size.

<div editor-title=".dstack/workflows/train-pipeline.yaml"> 

```yaml
workflows:
  - name: train-pipeline
    provider: bash
    commands:
      - pip install -r requirements.txt
      - python train.py
    artifacts:
      - ./lightning_logs
    resources:
      gpu:
        name: V100
      interruptible: true
```

</div>

!!! info "NOTE:"
    The [`interruptible`](../reference/providers/bash.md#resources) property instructs `dstack` to use spot instances, which may not always be available. However, when they
    are, they are significantly cheaper.

## Setting up the environment

You can use `pip` and `conda` executables to install packages and set up the environment.

Use the [`python`](../reference/providers/bash.md) property to specify a version of Python for pre-installation. Otherwise, `dstack` uses the local version.

[//]: # (TODO [MAJOR]: Currently, there is no way to pre-build the environment)

#### Using Docker

To run the pipeline with your custom Docker image, you can use the [`docker`](../reference/providers/docker.md) provider.

<div editor-title=".dstack/workflows/train-pipeline.yaml"> 

```yaml
workflows:
  - name: train-pipeline
    provider: bash
    image: 1.9.1-cuda11.1-cudnn8-runtime
    commands:
      - pip install -r requirements.txt
      - python train.py
    artifacts:
      - ./lightning_logs
```

</div>

[//]: # (TODO [MEDIUM]: Make a note that a custom Docker image might not have the right CUDA driver configured)

## Exposing ports

If you want the pipeline to serve web apps, specify the number of ports via the 
[`ports`](../reference/providers/bash.md#ports) property. They'll be
passed to the run as environment variables like `PORT_0`, `PORT_1`, etc.

<div editor-title=".dstack/workflows/train-pipeline.yaml"> 

```yaml
workflows:
  - name: train-pipeline
    provider: bash
    ports: 1
    commands:
      - pip install -r requirements.txt
      - tensorboard --port $PORT_0 --host 0.0.0.0 --logdir ./lightning_logs &
      - python train.py
    artifacts:
      - ./lightning_logs
```

</div>

[//]: # (TODO [MAJOR]: Currently, you can't choose ports yourself)

`dstack` automatically forwards ports to your local machine. You'll see the URLs to access each port in the
output.

[//]: # (TODO [MAJOR]: Currently, it requires the user to hardcode `--host 0.0.0.0`)

## Configuring cache

When running a pipeline, you may need to download files like pre-trained models, external data, or Python
packages. To avoid downloading them on each run of your pipeline, you can choose
which paths to cache between runs. 

<div editor-title=".dstack/workflows/train-pipeline.yaml"> 

```yaml
workflows:
  - name: train-pipeline
    provider: bash
    commands:
      - pip install -r requirements.txt
      - python train.py
    cache:
      - ./data
      - ~/.cache/pip
    artifacts:
      - ./lightning_logs
    resources:
      gpu:
        name: P100
```

</div>

!!! info "NOTE:"
    Cache saves files in the configured storage and downloads them at startup. This improves performance and saves you 
    from data transfer costs.

#### Cleaning up the cache

To clean up the cache, use the [`dstack prune cache`](../reference/cli/prune.md) CLI command, followed by the name of the configuration.

[//]: # (TODO [MAJOR]: Currently, there is no way to run distributed jobs and use distributed frameworks, such as PyTorch DDP, Ray, Spark, etc)

!!! info "NOTE:"
    Check out the [`dstackai/dstack-examples`](https://github.com/dstackai/dstack-examples/blob/main/README.md) repo for source code and other examples.