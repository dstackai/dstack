# What is dstack?

##### dstack is the modern CI/CD made for training models

dstack allows you to automate training workflows, version and reuse
data and models using a cloud vendor of your choice.

## Principles

### 🤖 Infrastructure as code

Typical data and training workflows deal with processing huge amounts of data. They typically involve
piping together numerous tasks that may have different hardware requirements.

dstack allows you to define workflows and infrastructure requirements as code using declarative configuration files. 
When you run a workflow, dstack provisions the required infrastructure on-demand.

When defining a workflow, you can either use the built-in providers (that support specific use-cases), 
or create custom providers for specific use-cases using dstack's Python API.

### 🧬 Made for continuous training

Training models doesn't end when you ship your model to production. It only starts there. Once your model is deployed,
it’s critical to observe the model, back-track issues that occur to the model to the steps of the training pipeline, fix
these issues, re-train on new data, validate, and re-deploy your model.

dstack allows you to build a pipeline that can run on a regular basis.

### 🤝 Designed for collaboration and reuse

dstack allows you to collaborate in multiple ways. On the one hand, the outputs of workflows, such as data and models
can be tagged and reused in other workflows within your team or across.
On the other hand, it's possible to reuse the providers built by other teams or by the community.

### 🪛 Technology-agnostic

With dstack, you can use any languages (`Python`, `R`, `Scala`, or any other), any frameworks (including the distributed
frameworks, such as `Dask`, `Ray`, `Spark`, `Tensorflow`, `PyTorch`, and any others), any experiment trackers,
any computing vendors or your own hardware.

## Quick tour

### 🧬 Workflows

#### Configuration files

Workflows are defined in the `.dstack/workflows.yaml` file within your project. 

If you plan to pass variables to your workflows when you run them, you have to describe these variables in the 
`.dstack/variables.yaml` file, next to workflows.

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: prepare
        provider: python
        python_script: prepare.py
        artifacts:
          - data
        resources:
          gpu: ${{ pgpu }}
    ```

=== ".dstack/variables.yaml"

    ```yaml
    variables:
      prepare:
        pgpu: 1
    ```

#### Command-line interface

To run this `Workflow`, use the following command of the dstack `CLI`:

```bash
dstack run prepare --pgpu 4
```

Once you do that, you'll see this run in the user interface. Shortly, dstack will assign it to one of the available 
runners or to a runner provisioned from a computing vendor that is configured for your account.

#### Tags

When the run is completed, you can assign a tag to it, e.g. `latest`. 
    
If you do that, you later can refer to this tagged workflow from other workflows:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: prepare
        provider: python
        python_script: prepare.py
        artifacts:
          - data
        resources:
          gpu: ${{ pgpu }}

      - name: train
        provider: python
        python_script: train.py
        artifacts:
          - checkpoint
        depends-on:
          - prepare:latest
        resources:
          gpu: ${{ tgpu }}     
    ```

=== ".dstack/variables.yaml"

    ```yaml
    variables:
      prepare:
        pgpu: 1

      train:
        tgpu: 1
    ```

When you run the `train` workflow, dstack will mount to it the `data` folder produced by the `prepare:latest`.

### 🤖 Runners

There are two ways to provision infrastructure: by using on-demand or self-hosted runners.

#### On-demand runners

To use on-demand runners, go to the `Settings`, then `AWS`, provide your credentials, and configure limits:

![](images/dstack_on_demand_settings.png){ lazy=true width="925" }

Once you configure these limits, runners will be provisioned automatically for the time of the run.

#### Self-hosted runners

As an alternative to on-demand runners, you can use your own hardware to run workflows.

To use your own server with dstack, you need to install the `dstack-runner` daemon there:

```bash
curl -fsSL https://get.dstack.ai/runner -o get-dstack-runner.sh
sudo sh get-dstack-runner.sh
```