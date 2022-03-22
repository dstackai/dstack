# What is dstack?

dstack is an open-core platform to train deep learning models 🧪, provision infrastructure on-demand 🤖, 
manage data 📦 , and version models 🧬.

## Principles

As an AI researcher 👩🏽‍🔬, you always want to focus on the experiments 🧪 with the model and its architecture 🏛.

However, training production-grade models 👷🏽‍ involves multiple steps, e.g. preparing data, training, model validation, etc.

### 🤖 Infrastructure management

Certain steps of your training pipeline, may require quite a bit of engineering efforts 
for managing data and infrastructure. As a team of AI researchers, you certainly don't want to be distracted 
by this all the time.

With dstack, you can define all steps together with the infrastructure they need via code, and run them interactively.
The infrastructure will be provisioned automatically and torn down once it's not needed.
The output of every step will be stored in an immutable storage.

### ✍️ Model provenance

If you want to be always know the exact steps that led you to getting a particular model (e.g. which you deployed to production),
it's important to track every step of your training pipeline along with their intermediate artifacts.

Because dstack tracks this all, any final result of your pipeline can be easily back-tracked to the previous steps and
exact data and code that led to this result.

## Quick tour

Here's a quick overview of how to use dstack.  

### 🧬 Workflows

#### Configuration files

Workflows must be defined in the `./dstack/workflows.yaml` file inside your project directory. 

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
          v100/gpu: ${{ pgpu }}
    ```

=== ".dstack/variables.yaml"

    ```yaml
    variables:
      prepare:
        pgpu: 1
    ```

#### Command-line interface

To run this workflow, use the following command of the dstack CLI:

```bash
dstack run prepare --pgpu 4
```

Once you do that, you'll see this run in the user interface. Shortly, dstack will assign it to one of the available 
runners or to a runner provisioned from a cloud account that is configured for your account.

#### Run tags

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
          v100/gpu: ${{ pgpu }}

      - name: train
        provider: python
        python_script: train.py
        artifacts:
          - checkpoint
        depends-on:
          - prepare:latest
        resources:
          v100/gpu: ${{ tgpu }}     
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

There are two ways to provision infrastructure: by using `on-demand` or `self-hosted` runners.

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

For a more detailed tutorial on how to get started with dstack, proceed
to [Quickstart](quickstart.md).