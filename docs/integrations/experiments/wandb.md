# Weights & Biases

Using W&B with `dstack` is a straightforward process.

## 1. Configure the API key

To use the W&B API in your workflow, you need to configure your API key.

First, go to [wandb.ai/authorize](https://wandb.ai/authorize), copy the value, and add it to `dstack` as a secret:

```shell hl_lines="1"
dstack secrets add WANDB_API_KEY acd0a9d1ebe3a4e4854d2f6a7cef85b5257f8183 
```

Now, your API token will be passed to the workflow via the `WANDB_API_KEY` environment variable when you run any
workflow.

!!! info "NOTE:"
    Secrets are set up per repository, and they can only be used by workflows that run within that repo. 

You can test if it's working by using the following example:

=== "`.dstack/workflows/wandb.yaml`"
    ```yaml
    workflows:
      - name: wandb-login
        provider: bash
        commands:
          - pip install wandb
          - wandb login
    ```

Run it locally to see if it works:

```shell hl_lines="1"
dstack run wandb-login
```

If it works, you'll see the following output:

```shell hl_lines="1"
 RUN            WORKFLOW     SUBMITTED  OWNER           STATUS     TAG  BACKENDS
 dull-turkey-1  wandb-login  now        peterschmidt85  Submitted       local

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

wandb: Currently logged in as: peterschmidt85. Use `wandb login --relogin` to force relogin
```

## 2. Create a run

Now that you've checked that the API Key is configured, you can use the W&B Python API to create a run and track metrics
from your Python script.

First, create a run with [`wandb.init()`](https://docs.wandb.ai/ref/python/run):

```python
import os

import wandb

wandb.init(project="my-awesome-project", name=os.getenv("RUN_NAME"))
```

!!! info "NOTE:"
    We're passing `os.getenv("RUN_NAME")` which contains the name of our `dstack` run, to the W&B run to match `dstack`'s
    run and W&B's run.

## 3. Track metrics

Now, we can use [`wandb.log()`](https://docs.wandb.ai/ref/python/log) and other APIs to track metrics from your training
code:

```python
wandb.log({'accuracy': train_acc, 'loss': train_loss})
```

Here's the full code example:

=== "`.dstack/workflows/wandb.yaml`"
    ```yaml
    workflows:
      - name: wandb-init
        provider: bash
        commands:
          - pip install wandb
          - python integrations/wandb/main.py
    ```

=== "`integrations/wandb/main.py`"
    ```python
    import os

    import wandb
    
    wandb.init(project="my-awesome-project", name=os.getenv("RUN_NAME"))
    ```

Running wandb-init will create the corresponding run in the W&B user interface. If you tracked metrics 
with [`wandb.log()`](https://docs.wandb.ai/ref/python/log), they would appear in real-time.

!!! info "NOTE:"
    If your workflow runs locally, it will run remotely with no issues as well. If you have a remote configured, you can run
    your workflow remotely using the `dstack run` command with the `--remote` flag.