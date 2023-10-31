# Fine-tuning

With `dstack`, fine-tuning generative AI models using [tasks](tasks.md) offers maximum flexibility. 
For a simpler out-of-the-box solution, try our fine-grained API. This API allows you to fine-tune any 
Hugging Face model with SFT or DPO techniques in your cloud with just one line of code. 

First, you connect to the `dstack` server:

```python
from dstack.api import Client, ClientError

try:
    client = Client.from_config()
except ClientError:
    print("Can't connect to the server")
```

Then, you create a fine-tuning task:

```python
from dstack.api.huggingface import SFTFineTuningTask

task = SFTFineTuningTask(model_name="NousResearch/Llama-2-13b-hf",
                         dataset_name="peterschmidt85/samsum",
                         num_train_epochs=2,
                         env={
                             "HUGGING_FACE_HUB_TOKEN": "...",
                         })
```

The task requires the `HUGGING_FACE_HUB_TOKEN` environment
variable and allows configuration of [various training parameters](../../docs/reference/api/python/index.md#dstack.api.huggingface.SFTFineTuningTask).

And finally, submit the task:

```python
from dstack.api import Resources, GPU

run = client.runs.submit(
    run_name="Llama-2-13b-samsum", # (Optional) If unset, its chosen randomly
    configuration=task,
    resources=Resources(gpu=GPU(memory="24GB", count=4)),
)
```

When submitting a task, you can configure resources, along with [many other options](../../docs/reference/api/python/index.md#dstack.api.RunCollection.submit).

You can use the [methods](../../docs/reference/api/python/index.md#dstack.api.Client) on `client` to manage your runs, including getting a list of runs, stopping a given
run, etc.

To track experiment metrics, specify `report_to` and related authentication environment variables.

```python
task = SFTFineTuningTask(model_name="NousResearch/Llama-2-13b-hf",
                         dataset_name="peterschmidt85/samsum",
                         num_train_epochs=2,
                         report_to="wandb",
                         env={
                             "HUGGING_FACE_HUB_TOKEN": "...",
                             "WANDB_API_KEY": "...",
                             "WANDB_PROJECT": ...
                         })
```

Currently, the API supports `"tensorboard"` and `"wandb"`:

![](../../assets/images/dstack-finetuning-wandb.png){ width=800 }

When the training is done, `dstack` pushes the final model to the Hugging Face hub.

![](../../assets/images/dstack-finetuning-hf.png){ width=800 }