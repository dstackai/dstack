# Workflows

[//]: # (Data and training workflows often deal with processing huge amounts of data. These workflows)
[//]: # (may involve piping together numerous tasks that may have different hardware requirements. )
[//]: # ()
[//]: # (With dstack, you can automate these workflows easily using declarative config files. Once you've defined)
[//]: # (your workflows, you can run any of them either manually or via external triggers. As workflows are running,)
[//]: # (dstack provisions the required infrastructure on-demand and tears it down once the workflows are finished.)

[//]: # (## Define files)

Workflows are defined in the `.dstack/workflows.yaml` file within your project.

If you'd like to parametrize your workflows, you can define variables in the `.dstack/variables.yaml` file next to your
workflows.

### Workflow syntax

The root element of the `.dstack/workflows.yaml` file is always `workflows`. 

It's an array of workflow, where each item may have the following parameters:

| Name         | Required | Description                                                |
|--------------|----------|------------------------------------------------------------|
| `name`       | Yes      | The name of our workflow                                   |
| `provider`   | Yes      | The provider that we want to use for our workflow          |
| `depends-on` | No       | The list of other workflows our workflow depends on if any |
| `...`        |          | Any parameters required by the provider                    |

[//]: # (!!! warning "Running workflows")
[//]: # (    In order to run the workflows defined in a project, the project must be under Git. At the same time, you don't need to)
[//]: # (    commit and push your local changes before running workflows. dstack tracks the local changes within the repository)
[//]: # (    when running a workflow.)

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

In the example above, if we run the `train` workflow, dstack will run two workflows sequentially: `prepare` and `train`.

If you'd like to avoid an unnecessary run of the `prepare` workflow, and instead use the output of one of the previous
runs, you can use tags.

To do that, you'll have to run the `prepare` workflow once, then assign a tag to it (e.g. `latest`), and then, refer to
this tag from the `train` workflow:

```bash
depends-on:
 - prepare:latest
```

### Providers

A workflow provider is program that creates the actual jobs per workflow according to the 
workflow parameters. You can use either the built-in providers or custom providers.

!!! info ""
    If you'd like to use a custom provider from another repository, you must use the following syntax:
    
    ```yaml
    provider:
      repo: https://github.com/dstackai/dstack
      name: python
    ```

Below, is the list of built-in providers:

[//]: # (TODO: Move built-in providers into a separate guide)

#### Python

The `python` provider runs a Python script on a single machine with required resources.

Here's the parameters supported by the provider:

| Parameter             | Required | Description                                         |
|-----------------------|----------|-----------------------------------------------------|
| `python_script`       | Yes      | The Python script with arguments                    |
| `requirements`        | No       | The list of Python packages required by the script. |
| `python`              | No       | The major Python version. By default, is `3.10`.    |
| `environment`         | No       | The list of environment variables and their values  |
| `artifacts`           | No       | The list of output artifacts                        |
| `resources`           | No       | The resources required to run the workflow          |
| `resources.cpu`       | No       | The required number of CPUs                         |
| `resources.memory`    | No       | The required amount of memory                       |
| `resources.gpu`       | No       | The required number of GPUs                         |

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

The `curl` provider downloads a file by a URL.

Here's the parameters supported by the provider:

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

[//]: # (#### Custom providers)

[//]: # (If you'd like to implement your custom logic of creating jobs per workflow, you can build your own custom provider. )
[//]: # (Learn more on how this can be done by reading the [corresponding guide]&#40;custom-providers.md&#41;.)

[//]: # (TODO: Running workflows)