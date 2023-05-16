# Pipelines

Pipelines allow to process data, train or fine-tune models, do batch inference or any other tasks
based on a pre-defined configuration.

With `dstack`, you can define such configurations as code and run your job with a single command, either locally or in the cloud account you prefer.

## Creating a configuration file

A configuration can be defined as a YAML file (under the `.dstack/workflows` directory).

<div editor-title=".dstack/workflows/hello.yaml"> 

```yaml
workflows:
  - name: hello
    provider: bash
    commands:
      - echo "Hello, world!"
    resources:
      gpu:
        name: V100
        count: 1
```

</div>

The configuration allows you to customize hardware resources, set up the Python environment, output artifacts, 
expose ports, configure cache, and more.

[//]: # (TODO [MAJOR]: IT supports only YAML and doesn't allow to define and run jobs using pure Python)

[//]: # (TODO [MAJOR]: Currently, it doesn't allow to define multiple steps)

## Running a pipeline

Once a configuration is defined, you can run it using the `dstack run` command:

<div class="termy">

```shell
$ dstack run hello

RUN      WORKFLOW  SUBMITTED  STATUS     TAG
shady-1  hello     now        Submitted  
 
Provisioning... It may take up to a minute. ✓

To exit, press Ctrl+C.

Hello, world!
```

</div>

For convenience, `dstack` uses an exact copy of the source code that is locally present in the folder where you use the `dstack` command.

??? info "Using .gitignore"
    If you don't want the pipeline to sync certain files (especially large local files that are not needed
    for the pipeline), feel free to add them to the `.gitignore` file. In this case, `dstack` will ignore them,
    even if you aren't using Git.

If you configure a project to run pipelines in the cloud, `dstack` will automatically provision the required cloud
resources. After the workflow is finished, `dstack` will automatically save output artifacts and clean up the cloud resources.

??? info "Configuring projects"
    The default project runs pipelines locally. However, you can
    log into Hub and configure additional projects to run pipelines in a cloud account of your choice. 

    You can configure multiple projects and pass the project name to the CLI by using the `--project` argument.

#### Stopping a run

To stop the run, click `Ctrl`+`C` while the `dstack run` command is running,
or use the `dstack stop` command. `dstack` will automatically save the output artifacts and clean up any cloud resources 
if they are used.

## Saving output artifacts

The pipeline configuration may use the `artifacts` property to specify the paths to the folders that must be saved as 
output artifacts.

<div editor-title=".dstack/workflows/hello-txt.yaml"> 

```yaml
workflows:
  - name: hello-txt
    provider: bash
    commands:
      - echo "Hello, world!" > output/hello.txt
    artifacts:
      - path: output
```

</div>

The artifacts are saved at the end of the run, such as when it's stopped or finished.

[//]: # (TODO [MAJOR]: It doesn't allow to save artifacts via Python API)

## Configuring hardware resources

If your project is configured to run pipelines in the cloud, you can use the `resources` property in the YAML file to 
request hardware resources like memory, GPUs, and shared memory size.

Additionally, you can choose whether dstack should use interruptible instances (also known as spot instances).

<div editor-title=".dstack/workflows/hello.yaml"> 

```yaml
workflows:
  - name: hello
    provider: bash
    commands:
      - echo "Hello, world!"
    resources:
      gpu:
        name: V100
        count: 1
      interruptible: true
```

</div>

## Setting up the environment

You can use `pip` and `conda` executables to install packages and set up the environment.

Use the `python` property to specify a version of Python for pre-installation. Otherwise, `dstack` uses the local version.

<div editor-title=".dstack/workflows/hello.yaml"> 

```yaml
workflows:
  - name: hello
    provider: bash
    python: 3.11
    commands:
      - conda install pandas
      - conda list | grep pandas
```

</div>

[//]: # (TODO [MAJOR]: Currently, there is no way to pre-build the environment)

#### Using Docker

To run the pipeline with your custom Docker image, you can use the `docker` provider.

<div editor-title=".dstack/workflows/hello-docker.yaml"> 

```yaml
workflows:
  - name: hello-docker
    provider: docker
    image: ubuntu
    commands:
      - echo "Hello, world!"
```

</div>

## Exposing ports

Your pipeline may configure ports to serve web apps.

<div editor-title=".dstack/workflows/hello-tensorboard.yaml"> 

```yaml
workflows:
  - name: train-tensorboard
    provider: bash
    ports: 1
    commands:
      - pip install torchvision pytorch-lightning tensorboard
      - tensorboard --port $PORT_0 --host 0.0.0.0 --logdir ./lightning_logs &
      - python tutorials/tensorboard/train.py
    artifacts:
      - path: ./lightning_logs
```

</div>

[//]: # (TODO [MAJOR]: Currently, you can't choose ports yourself)

To run web apps, specify the number of ports via the `ports` property. They'll be
passed to the run as environment variables like `PORT_0`, `PORT_1`, etc.

`dstack` will automatically forward ports to your local machine. You'll see the URLs to access each port in the
output.

## Configuring cache

When running a pipeline, you may need to download files like pre-trained models, external data, or Python
packages. To avoid downloading them on each run of your pipeline, you can choose
which paths to cache between runs. 

<div editor-title=".dstack/workflows/hello-cache.yaml"> 

```yaml
workflows:
  - name: hello-cache
    provider: bash
    commands:
      - pip install torchvision
      - pip list | grep torchvision
    cache:
      - ~/.cache/pip
```

</div>

!!! info "NOTE:"
    Cache saves files in its own storage and downloads them at startup. This improves performance and saves you 
    from data transfer costs.

#### Cleaning up the cache

To clean up the cache, use the `dstack prune cache` CLI command, followed by the name of the configuration.

[//]: # (TODO [MAJOR]: Currently, there is no way to run distributed jobs and use distributed frameworks, such as PyTorch DDP, Ray, Spark, etc)