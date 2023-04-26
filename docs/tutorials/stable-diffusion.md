---
title: Generate images with Stable Diffusion
---

# Generate images with Stable Diffusion

This tutorial demonstrates how to generate images using a pretrained Stable Diffusion model.

!!! info "NOTE:"
    The source code of this tutorial is available in the <a href="https://github.com/dstackai/dstack-playground#readme" target="__blank">Playground</a>.

## 1. Requirements

Here is the list of Python libraries that we will use:

<div editor-title="tutorials/stable_diffusion/requirements.txt"> 

```txt
diffusers
transformers
scipy
ftfy
accelerate
safetensors
```

</div>

!!! info "NOTE:"
    We're using the [`safetensors`](https://github.com/huggingface/safetensors) library because it implements a new simple format for storing tensors safely (as opposed
    to pickle) and that is still fast (zero-copy).

To ensure our scripts can run smoothly across all environments, let's include them in
the `tutorials/stable_diffusion/requirements.txt` file.

You can also install these libraries locally:

<div class="termy">

```shell
$ pip install -r tutorials/stable_diffusion/requirements.txt
```

</div>

Also, because we'll use `dstack` CLI, let's install it locally:

<div class="termy">

```shell
$ pip install dstack -U
```

</div>

## 2. Download the pre-trained model

In our tutorial, we'll use the [`runwayml/stable-diffusion-v1-5`](https://huggingface.co/runwayml/stable-diffusion-v1-5) model (pretrained by Runway).

Let's create the following Python file:

<div editor-title="stable_diffusion/stable_diffusion.py"> 

```python
from huggingface_hub import snapshot_download

if __name__ == '__main__':
    snapshot_download("runwayml/stable-diffusion-v1-5", local_dir="./models/runwayml/stable-diffusion-v1-5")
```

</div>

In order to run a script via `dstack`, the script must be defined as a workflow via a YAML file
under `.dstack/workflows`.

Let's define the following workflow YAML file:

<div editor-title=".dstack/workflows/stable_diffusion.yaml"> 

```yaml
workflows:
  - name: stable-diffusion
    provider: bash
    commands:
      - pip install -r tutorials/stable_diffusion/requirements.txt
      - python tutorials/stable_diffusion/stable_diffusion.py
    artifacts:
      - path: ./models
    resources:
      memory: 16GB
```

</div>

Now, the workflow can be run anywhere via the `dstack` CLI.

!!! info "NOTE:"
    Before you run a workflow via `dstack`, make sure your project has a remote Git branch configured,
    and invoke the `dstack init` command which will ensure that `dstack` may access the repository:

    <div class="termy">

    ```shell
    $ dstack init
    ```

    </div>

Here's how to run a `dstack` workflow locally:

<div class="termy">

```shell
$ dstack run stable-diffusion
```

</div>

Once you run it, `dstack` will run the script, and save the `models` folder as an artifact.
After that, you can reuse it in other workflows.

## 3. Create a dev environment

Sometimes, before you can run a workflow, you may want to run code interactively,
e.g. via an IDE or a notebook.

Look at the following example:

<div editor-title=".dstack/workflows/stable_diffusion.yaml"> 

```yaml
workflows:
  - name: code-stable
    provider: code
    deps:
      - workflow: stable-diffusion
    setup:
      - pip install -r tutorials/stable_diffusion/requirements.txt
    resources:
      memory: 16GB
```

</div>

As you see, the `code-stable` workflow refers the `stable-diffusion` workflow as a dependency.

If you run it, `dstack` will run a VS Code application with the code, pretrained model,
and Python environment:

<div class="termy">

```shell 
$ dstack run code-stable
```

</div>

## 4. Run locally

Let's write a script that generates images using a pre-trained model and given prompts:

<div editor-title="stable_diffusion/prompt_stable.py"> 

```python
import argparse
from pathlib import Path

import torch
from diffusers import StableDiffusionPipeline

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-P", "--prompt", action='append', required=True)
    args = parser.parse_args()

    pipe = StableDiffusionPipeline.from_pretrained("./models/runwayml/stable-diffusion-v1-5", local_files_only=True)
    if torch.cuda.is_available():
        pipe.to("cuda")
    images = pipe(args.prompt).images

    output = Path("./output")
    output.mkdir(parents=True, exist_ok=True)
    for i in range(len(images)):
        images[i].save(output / f"{i}.png")
```

</div>

The script loads the model from the local `models` folder, generates images and saves them to the 
local `output` folder.

Let's define it in our workflow YAML file:

<div editor-title=".dstack/workflows/stable_diffusion.yaml"> 

```yaml
workflows:
  - name: prompt-stable
    provider: bash
    deps:
      - workflow: stable-diffusion
    commands:
      - pip install -r tutorials/stable_diffusion/requirements.txt
      - python tutorials/stable_diffusion/prompt_stable.py ${{ run.args }}
    artifacts:
      - path: ./output
    resources:
      memory: 16GB
```

</div>

!!! info "NOTE:"
    The `dstack run` command allows to pass arguments to the workflow via `${{ run.args }}`.

Let's run the workflow locally:

<div class="termy">

```shell
$ dstack run prompt-stable -P "cats in hats" 
```

</div>

The output artifacts of local runs are stored under `~/.dstack/artifacts`.

Here's an example of the `prompt-stable` workflow output:

![cats in hats](cats-in-hats.png)

## 5. Run remotely

!!! info "NOTE:"
    To run workflows remotely in a configured cloud, we'll need the [Hub application](../docs/quick-start.md#start-the-hub-application).

Once the remote is configured, we can use the [`dstack run`](../docs/reference/cli/run.md) command with the `--remote` flag to
run our workflow in the cloud.

Let's first run the `stable-diffusion` workflow:

<div class="termy">

```shell
$ dstack run stable-diffusion --remote
```

</div>

!!! info "NOTE:"
    When you run a remote workflow, `dstack` automatically creates resources in the configured cloud,
    and releases them once the workflow is finished.

Now, you can run the `prompt-stable` remotely as well:

<div class="termy">

```shell
dstack run prompt-stable --remote --gpu-name V100 -P "cats in hats"
```

</div>

!!! info "NOTE:"
    You can configure the required resources to run the workflows either via the `resources` property in YAML
    or the `dstack run` command's arguments, such as `--gpu`, `--gpu-name`, etc.