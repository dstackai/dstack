---
title: Generate images with Stable Diffusion
---

# Generate images with Stable Diffusion

This tutorial will show you how to run and debug a Gradio application on your cloud account that generates images using
Stable Diffusion.

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
gradio
```

</div>

!!! info "NOTE:"
    We're using the [`safetensors`](https://github.com/huggingface/safetensors) library because it implements a new simple format for storing tensors safely (as opposed
    to pickle) and that is still fast (zero-copy).

## 2. Download the model

In our tutorial, we'll use the [`runwayml/stable-diffusion-v1-5`](https://huggingface.co/runwayml/stable-diffusion-v1-5) model (pretrained by Runway).

```python
from huggingface_hub import snapshot_download

model_name = "runwayml/stable-diffusion-v1-5"

snapshot_download(model_name, local_dir=f".models/{model_name}")
```

Once it's downloaded, you can load it to generate images based on a prompt:

```python
from diffusers import StableDiffusionPipeline

pipe = StableDiffusionPipeline.from_pretrained(f"./models/{model_name}", device_map="auto", local_files_only=True)

prompt = "a photo of an astronaut riding a horse on mars"
image = pipe(prompt).images[0]  
    
image.save("astronaut_rides_horse.png")
```

## 3. Create the application

Now, let's put it all together into a simple Gradio application.

Here's the complete code.

<div editor-title="tutorials/dolly/chat.py">

```python
import os
from pathlib import Path

import gradio as gr
from diffusers import StableDiffusionPipeline
from huggingface_hub import snapshot_download

model_name = "runwayml/stable-diffusion-v1-5"

local_dir = f"./models/{model_name}"
if not Path(local_dir).exists() or len(os.listdir(local_dir)) == 0:
    snapshot_download(model_name, local_dir=local_dir)

pipe = StableDiffusionPipeline.from_pretrained(f"./models/{model_name}", device_map="auto", local_files_only=True)

theme = gr.themes.Monochrome(
    primary_hue="indigo",
    secondary_hue="blue",
    neutral_hue="slate",
    radius_size=gr.themes.sizes.radius_sm,
    font=[gr.themes.GoogleFont("Open Sans"), "ui-sans-serif", "system-ui", "sans-serif"],
)

with gr.Blocks(theme=theme) as demo:
    def infer(prompt):
        return pipe([prompt]).images


    with gr.Row():
        text = gr.Textbox(
            show_label=False,
            max_lines=1,
            placeholder="Enter your prompt",
        ).style(container=False)
        btn = gr.Button("Generate image").style(full_width=False)

    gallery = gr.Gallery(
        show_label=False
    ).style(columns=[2], height="auto")

    text.submit(infer, inputs=text, outputs=[gallery])
    btn.click(infer, inputs=text, outputs=[gallery])

if __name__ == "__main__":
    server_port = int(os.getenv("PORT_0")) if os.getenv("PORT_0") else None
    demo.launch(server_name="0.0.0.0", server_port=server_port)
```

</div>

!!! info "NOTE:"
    Since we'll run our application via `dstack`, we've added the possibility to override the server port of our application
    using the `PORT_0` environment variable.

## 4. Define the workflow

To run our application in our cloud account using `dstack`, we need to define a `dstack` workflow as follows:

<div editor-title=".dstack/workflows/dolly.yaml"> 

```yaml
workflows:
  - name: stable-diffusion
    provider: bash
    ports: 1
    commands:
      - pip install -r tutorials/stable_diffusion/requirements.txt
      - python tutorials/stable_diffusion/app.py
    cache:
      - ~/.cache/pip
    resources:
      gpu:
        count: 1
      memory: 16GB
      interruptible: true
```

</div>

!!! info "NOTE:"
    We define a `dstack` workflow file to specify the requirements, script, ports, cached files, and hardware resources for
    our application. Our workflow requires a GPU and at least 16GB of memory and interruptible (spot) instances if
    run in the cloud. 

## 5. Run the workflow

!!! info "NOTE:"
    Before running the workflow, make sure that you have set up the Hub application and
    [created a project](../docs/quick-start.md#create-a-hub-project) that can run workflows in the cloud.

Once the project is configured, we can use the [`dstack run`](../docs/reference/cli/run.md) command to
run our workflow.

!!! info "NOTE:"
    The Hub will automatically create the corresponding cloud resources, run the application, and forward the application
    port to localhost. If the workflow is completed, it automatically destroys the cloud resources.

<div class="termy">

```shell
$ dstack run stable-diffusion

RUN       WORKFLOW          SUBMITTED  STATUS     TAG
turtle-1  stable-diffusion  now        Submitted     

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Downloading model files: 
---> 100%

Running on local URL:  http://127.0.0.1:51741
```

</div>

Clicking the URL from the output will open our Gradio application running in the cloud. 

![](dstack-stable-diffusion.png){ width=800 }

## 6. Debug the workflow

Before coming up with a workflow that runs perfectly in the cloud, you may need to debug it. With `dstack`, you can debug
your workflow right in the cloud using an IDE. One way to do this is by using
the [`code`](../docs/reference/providers/code.md) provider.

Define the following workflow:

<div editor-title=".dstack/workflows/dolly.yaml"> 

```yaml
workflows:
  - name: debug-stable-diffusion
    provider: code
    ports: 1
    setup:
      - pip install -r tutorials/stable_diffusion/requirements.txt
    cache:
      - ~/.cache/pip
    resources:
      gpu:
        count: 1
      memory: 16GB
      interruptible: true
```

</div>

If you run it, `dstack` will run a VS Code application with the code, dependencies, and hardware resources
you've specified.

<div class="termy">

```shell
$ dstack run debug-stable-diffusion

RUN        WORKFLOW                SUBMITTED  STATUS     TAG
mangust-1  debug-stable-diffusion  now        Submitted     

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

The PORT_0 port is mapped to http://0.0.0.0:51742

Web UI available at http://127.0.0.1:51741
```

</div>

Clicking the last link will open VS Code on the provisioned machine.

![](dstack-stable-diffusion-code.png)

You can run your code interactively, debug it, and run the application there.
After fixing the workflow, you can run it using the `bash` provider.

As an alternative to the `code` provider, you can run the `bash` provider with `ssh` set to `true`. This allows you to attach
your own IDE to the running workflow.