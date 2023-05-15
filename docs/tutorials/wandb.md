---
title: Track experiments with W&B
---

# Track experiments with W&B

Using `dstack` with Weights & Biases is a straightforward process.

## 1. Configure the API key

To use the W&B API in your workflow, you need to configure your API key.

First, go to [wandb.ai/authorize](https://wandb.ai/authorize), copy the value, and add it to `dstack` as a secret:

<div class="termy">

```shell
$ dstack secrets add WANDB_API_KEY acd0a9d1ebe3a4e4854d2f6a7cef85b5257f8183 
```

</div>

Now, your API token will be passed to the workflow via the `WANDB_API_KEY` environment variable when you run any
workflow.

!!! info "NOTE:"
    Secrets are set up per repository, and they can only be used by workflows that run within that repo. 

You can test if it's working by using the following example:

<div editor-title=".dstack/workflows/wandb.yaml"> 

```yaml
workflows:
  - name: wandb-login
    provider: bash
    commands:
      - pip install wandb
      - wandb login
```

</div>

Run it to see if it works:

<div class="termy">

```shell
$ dstack run wandb-login

RUN            WORKFLOW     SUBMITTED  STATUS     TAG  BACKENDS
dull-turkey-1  wandb-login  now        Submitted       local

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

wandb: Currently logged in as: peterschmidt85. Use `wandb login --relogin` to force relogin

$ 
```

</div>

## 2. Create a run

Now that you've checked that the API Key is configured, you can use the W&B Python API to create a run and track metrics
from your Python script.

First, create a run with [`wandb.init()`](https://docs.wandb.ai/ref/python/run):

<div editor-title="examples/wandb/main.py"> 

```python
import os

import wandb

wandb.init(project="my-awesome-project", name=os.getenv("RUN_NAME"))
```

</div>

!!! info "NOTE:"
    We're passing `os.getenv("RUN_NAME")` which contains the name of our `dstack` run, to the W&B run to match `dstack`'s
    run and W&B's run.

## 3. Track metrics

Now, we can use [`wandb.log()`](https://docs.wandb.ai/ref/python/log) and other APIs to track metrics from your training
code:

```python
wandb.log({'accuracy': train_acc, 'loss': train_loss})
```

Here's the workflow YAML file:

<div editor-title=".dstack/workflows/wandb.yaml"> 

```yaml
workflows:
  - name: wandb-init
    provider: bash
    commands:
      - pip install wandb
      - python examples/wandb/main.py
```

</div>

Running `wandb-init` will create the corresponding run in the W&B user interface. If you tracked metrics 
with [`wandb.log()`](https://docs.wandb.ai/ref/python/log), they would appear in real-time.