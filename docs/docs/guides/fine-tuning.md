# Fine-tuning

If you want to fine-tune an LLM based on a given dataset, consider using
`dstack`'s finetuning API.

You specify a model name, dataset on HuggingFace, and training parameters.
`dstack` takes care of the training and pushes it to the HuggingFace hub upon completion. 

You can use any cloud GPU provider(s) and experiment tracker of your choice.

## Create a client

First, you connect to `dstack`:

```python
from dstack.api import Client, ClientError

try:
    client = Client.from_config()
except ClientError:
    print("Can't connect to the server")
```

## Create a task

Then, you create a fine-tuning task, specifying the model and dataset, 
and various [training parameters](../../docs/reference/api/python/index.md#dstack.api.finetuning.SFTFineTuningTask).

```python
from dstack.api.finetuning import SFTFineTuningTask

task = SFTFineTuningTask(hf_model_name="NousResearch/Llama-2-13b-hf",
                         hf_dataset_name="peterschmidt85/samsum",
                         hf_token="...",
                         num_train_epochs=2)
```

!!! info "Dataset format"
    For the SFT fine-tuning method, the dataset should contain a `"text"` column with completions following the prompt format
    of the corresponding model.
    Check the [peterschmidt85/samsum](https://huggingface.co/datasets/peterschmidt85/samsum) example. 

## Submit the task

When submitting a task, you can configure resources, and many [other options](../../docs/reference/api/python/index.md#dstack.api.RunCollection.submit).

```python
from dstack.api import Resources, GPU

run = client.runs.submit(
    run_name="Llama-2-13b-samsum", # (Optional) If unset, its chosen randomly
    configuration=task,
    resources=Resources(gpu=GPU(memory="24GB")),
)
```

!!! info "Fine-tuning methods"
    The API currently supports only SFT, with support for DPO and other methods coming soon.

When the training is done, `dstack` pushes the final model to the Hugging Face hub.

![](../../assets/images/dstack-finetuning-hf.png){ width=800 }

## Manage runs

You can use the instance of [`dstack.api.Client`](../../docs/reference/api/python/index.md#dstack.api.Client) to manage your runs, 
including getting a list of runs, stopping a given run, etc.

## Track experiments

To track experiment metrics, specify `report_to` and related authentication environment variables.

```python
task = SFTFineTuningTask(hf_model_name="NousResearch/Llama-2-13b-hf",
                         hf_dataset_name="peterschmidt85/samsum",
                         hf_token="...",
                         report_to="wandb",
                         env={
                             "WANDB_API_KEY": "...",
                             "WANDB_PROJECT": "...",
                         },
                         num_train_epochs=2
                         )
```

Currently, the API supports `"tensorboard"` and `"wandb"`.

![](../../assets/images/dstack-finetuning-wandb.png){ width=800 }

[//]: # (TODO: Example)
[//]: # (TODO: Next steps)