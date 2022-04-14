# Workflows

[//]: # (Data and training workflows often deal with processing huge amounts of data. These workflows)
[//]: # (may involve piping together numerous tasks that may have different hardware requirements. )
[//]: # ()
[//]: # (With dstack, you can automate these workflows easily using declarative config files. Once you've defined)
[//]: # (your workflows, you can run any of them either manually or via external triggers. As workflows are running,)
[//]: # (dstack provisions the required infrastructure on-demand and tears it down once the workflows are finished.)

## Define workflows

`Workflows` are defined in the `.dstack/workflows.yaml` file within your project.

If you plan to pass `Variables` to your `Workflows` when you run them, you have to describe these `Variables` in the 
`.dstack/variables.yaml` file, next to `Workflows`.

### Syntax

The root element of the `.dstack/workflows.yaml` file is always `workflows`. 

It's an array, where each item represents a `Workflow` and may have the following parameters:

| Name         | Required         | Description                                                |
|--------------|------------------|------------------------------------------------------------|
| `name`       | :material-check: | The name of our workflow                                   |
| `provider`   | :material-check: | The provider that we want to use for our workflow          |
| `depends-on` |                  | The list of other workflows our workflow depends on if any |
| `...`        |                  | Any parameters required by the provider                    |

Here's an example:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      # This workflow loads and prepares data 
      - name: prepare
        # This workflow uses `python` provider
        provider: python
        python_script: prepare.py
        # The `data` folder will be tracked as an output artifact
        artifacts:
          - data
        # Here we use a variable to say whether we need GPU or not to run this workflow
        resources:
          gpu: ${{ pgpu }}

      # This workflow uses the data produced by the `prepare` workflow
      - name: train
        # This workflow uses `python` provider
        provider: python
        python_script: train.py
        # The `checkpoint` folder will be tracked as an output artifact
        artifacts:
          - checkpoint
        depends-on:
          - prepare
        resources:
          gpu: ${{ tgpu }}     
    ```

=== ".dstack/variables.yaml"

    ```yaml
    variables:
      prepare:
        pgpu: 0

      train:
        tgpu: 1
    ```

### Dependencies

In the example above, if we run the `train` `Workflow`, dstack will run two `Workflows` sequentially: `prepare` and `train`.

If you'd like to avoid running the `prepare` `Workflow` when running the `train` `Workflow`, and instead you'd like to use
the output of one of the previous `Runs`, you can use `Tags`.

To do that, you'll have to run the `prepare` `Workflow` once, then assign a `Tag` to it (e.g. `latest`), and then, refer to
this `Tag` from the `train` `Workflow`:

```yaml
depends-on:
 - prepare:latest
```

### Providers

A `Provider` is program that creates the actual `Jobs` per `Workflow` according to the 
`Workflow` parameters (specified in `.dstack/workflows.yaml`). You can use either the built-in `Providers` or custom 
`Providers`.

!!! info ""
    If you want to use a custom `Provider` from another repository, use the following syntax:
    
    ```yaml
    provider:
      repo: https://github.com/dstackai/dstack
      name: python
    ```

Below, is the list of built-in `Providers`.

#### Docker

The `Docker` `Provider` runs a Docker image on a single machine with required resources.

Here's the list of parameters supported by the provider:

| Parameter          | Required | Description                                         |
|--------------------|----------|-----------------------------------------------------|
| `image`            | Yes      | The Docker image.                                   |
| `commands`         | No       | The list of commands to run.                        |
| `artifacts`        | No       | The list of output artifacts.                       |
| `resources`        | No       | The resources required to run the workflow.         |
| `resources.cpu`    | No       | The required number of CPUs.                        |
| `resources.memory` | No       | The required amount of memory.                      |
| `resources.gpu`    | No       | The required number of GPUs.                        |

Example:

```yaml
workflows:
  - name: hello
    provider: docker
    image: ubuntu
    commands:
      - mkdir -p output
      - echo 'Hello, world!' > output/hello.txt
    artifacts:
      - output
    resources:
      cpu: 1
      memory: 1GB
```

#### Python

The `python` `Provider` runs a Python script on a single machine with required resources.

Here's the supported parameters:

| Parameter             | Required         | Description                                         |
|-----------------------|------------------|-----------------------------------------------------|
| `python_script`       | :material-check: | The Python script with arguments                    |
| `requirements`        |                  | The list of Python packages required by the script. |
| `python`              |                  | The major Python version. By default, is `3.10`.    |
| `environment`         |                  | The list of environment variables and their values  |
| `artifacts`           |                  | The list of output artifacts                        |
| `resources`           |                  | The resources required to run the workflow          |
| `resources.cpu`       |                  | The required number of CPUs                         |
| `resources.memory`    |                  | The required amount of memory                       |
| `resources.gpu`       |                  | The required number of GPUs                         |

Here's an example:

```yaml
workflows:
  - name: download-model  
    provider: python
    requirements: requirements.txt
    python_script: download_model.py
    environment:
      PYTHONPATH: src
    artifacts:
      - models
    resources:
      cpu: 2
      memory: 32GB
      gpu: 1
```

#### Curl

The `curl` `Provider` downloads a file by a URL.

Here's the supported parameters:

| Parameter     | Required | Description                     |
|---------------|----------|---------------------------------|
| `url`         | Yes      | The URL of the file to download |
| `output`      | Yes      | The path to store the file      |
| `artifacts`   | No       | The list of output artifacts    |

Here's an example:

```yaml
workflows:
  - name: download-dataset
    provider: curl
    url: https://github.com/karpathy/char-rnn/blob/master/data/tinyshakespeare/input.txt
    output: raw_dataset/input.txt
    artifacts:
      - raw_dataset
```

#### Custom providers

If you'd like to implement your custom logic of creating `Jobs` per `Workflow`, you can build your own custom `Provider`. 
Learn more on how this can be done by reading the [corresponding guide](custom-providers.md).

### Examples

You can find some examples of `Workflows` in [`dstackai/dstack-examples`](https://github.com/dstackai/dstack-examples) 
GitHub repository. Feel free to clone the repository and run any of the `Workflows` defined there. 

## Run workflows

!!! warning ""
    Note, before you can run `Workflows`, you have to [set up runners](quickstart.md#step-1-set-up-runners).

### Install the CLI

Before you can run workflows, you have to install the dstack `CLI`:

```bash
pip install dstack -U
```

Then, you have to configure the `CLI` with your `Token`:

```bash
dstack config --token <token>
```

Your `token` value can be found in `Settings`:

![](images/dstack_quickstart_token.png){ lazy=true width="1060" }

Once the `CLI` is installed and configured, you can go ahead and run any `Workflow` defined in
your `.dstack/workflows.yaml` file.

### Run workflows

```bash
dstack run train-mnist 
```

In case you want to override any of the `Variables` defined in `.dstack/variables.yaml` in your `Run`, you can do it
the following way:

```bash
dstack run train-mnist --gpu 2 --epoch 100 --seed 2
```

!!! warning "Git"
    In order to run `Workflows` defined in a project, the project must be under `Git`. 
    As to local changes, you don't have to commit them before running the `Workflow`. 
    dstack will track them automatically.

Once you run a `Workflow`, you'll see it in the `User Interface`. 
Once the `Provider` creates the `Jobs`, you'll see the `Jobs` under the `Run` if you select this `Run`.

![](images/dstack_quickstart_runs.png){ lazy=true width="1060" }

## Tag runs

When the `Run` is finished, you can assign a `Tag` to it, e.g. `latest`, either via the `User Interface` or the `CLI`.

Here's how to do it via the `CLI`:

```bash
dstack tag cowardly-goose-1 latest
```