---
title: Run your own ChatGPT with Dolly
status: new
---

# Run your own ChatGPT with Dolly

This tutorial shows you how to run (and debug) your own ChatGPT on your cloud account using `dstack`, Gradio, and
Dolly (Databricks' open-source pre-trained model).

!!! info "NOTE:"
    The source code of this tutorial is available in the [Playground](../playground.md).

## 1. Requirements

Here is the list of Python libraries that we will use:

<div editor-title="tutorials/dolly/requirements.txt"> 

```txt
transformers
accelerate
gradio
```

</div>

## 2. Download the model 

The heart of our ChatGPT application will be Dolly, the recently open-sourced pre-trained model. To use it in our
application, we first have to download it from HuggingFace's Hub:

```python
from huggingface_hub import snapshot_download

model_name = "databricks/dolly-v2-12b"

snapshot_download(model_name, local_dir=f".models/{model_name}")
```

Once it's downloaded, you can load it to generate text given a prompt:

```python
import torch
from transformers import pipeline

generate_text = pipeline(model=f".models/{model_name}", torch_dtype=torch.bfloat16, 
                         trust_remote_code=True, device_map="auto")

print(generate_text("Explain how large language models work"))
```

!!! info "NOTE:"
    In this tutorial, we use [`databricks/dolly-v2-12b`](https://huggingface.co/databricks/dolly-v2-12b), which is the
    largest variant of the model. Smaller options
    include [`databricks/dolly-v2-3b`](https://huggingface.co/databricks/dolly-v2-3b) and
    [`databricks/dolly-v2-7b`](https://huggingface.co/databricks/dolly-v2-7b).  

## 3. Create an application

Now, let's put it all together into a simple chat application. To do that, we'll use Gradio and its
built-in [`Chatbot`](https://gradio.app/creating-a-chatbot/) component.

Here's the complete code for our application:

<div editor-title="tutorials/dolly/chat.py">

```python
import os
from pathlib import Path

import gradio as gr
import torch
from huggingface_hub import snapshot_download
from transformers import pipeline

model_name = "databricks/dolly-v2-12b"

local_dir = f"./models/{model_name}"
if not Path(local_dir).exists() or len(os.listdir(local_dir)) == 0:
    snapshot_download(model_name, local_dir=local_dir)

generate_text = pipeline(model=local_dir, torch_dtype=torch.bfloat16, trust_remote_code=True,
                         device_map="auto")

theme = gr.themes.Monochrome(
    primary_hue="indigo",
    secondary_hue="blue",
    neutral_hue="slate",
    radius_size=gr.themes.sizes.radius_sm,
    font=[gr.themes.GoogleFont("Open Sans"), "ui-sans-serif", "system-ui", "sans-serif"],
)

with gr.Blocks(theme=theme) as demo:
    chatbot = gr.Chatbot()
    msg = gr.Textbox()
    clear = gr.Button("Clear")


    def user(user_message, history):
        return "", history + [[user_message, None]]


    def bot(history):
        history[-1][1] = generate_text(history[-1][0])
        return history


    msg.submit(user, [msg, chatbot], [msg, chatbot], queue=False).then(
        bot, chatbot, chatbot
    )
    clear.click(lambda: None, None, chatbot, queue=False)

if __name__ == "__main__":
    server_port = int(os.getenv("PORT_0")) if os.getenv("PORT_0") else None
    demo.launch(server_name="0.0.0.0", server_port=server_port)
```

</div> 

!!! info "NOTE:"
    Since we'll run our application via `dstack`, we've added the possibility to override the server port of our application
    using the `PORT_0` environment variable.

## 4. Define a workflow

To run our application in our cloud account using `dstack`, we need to define a `dstack` workflow as follows:

<div editor-title=".dstack/workflows/dolly.yaml"> 

```yaml
workflows:
  - name: dolly
    provider: bash
    ports: 1
    commands:
      - pip install -r tutorials/dolly/requirements.txt
      - python tutorials/dolly/chat.py
    cache:
      - ~/.cache/pip
    resources:
      gpu:
        name: A100
      memory: 60GB
      interruptible: true
```

</div>

!!! info "NOTE:"
    We define the dstack workflow file to specify the requirements, script, ports, cached files, and hardware resources for
    our application. Our workflow requires an A100 GPU with at least 60GB of memory and interruptible (spot) instances if
    run in the cloud. 

## 4. Run the workflow

Before we can run our workflow in our cloud account, we need to configure a remote using
the [`dstack config`](../setup/index.md#configure-a-remote) command:

<div class="termy">

```shell
$ dstack config

? Choose backend. Use arrows to move, type to filter
> [aws]
  [gcp]
  [hub]
```

</div>

After configuring the remote, we can use the [`dstack run`](../reference/cli/run.md) command with the `--remote` flag to
run our workflow in the cloud.

<div class="termy">

```shell
$ dstack run dolly --remote

RUN       WORKFLOW  SUBMITTED  STATUS     TAG  BACKENDS
turtle-1  dolly     now        Submitted       gcp

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Downloading model files: 
---> 100%

Running on local URL:  http://127.0.0.1:51741
```

</div>

!!! info "NOTE:"
    `dstack` automatically creates and sets up the corresponding cloud instance, runs the application, and forwards the
    application port to localhost. If the command is interrupted, `dstack` automatically destroys the cloud instance.

Clicking the URL from the output will open our ChatGPT application running in the cloud. 

![](dstack-dolly.png){ width=800 }

## 5. Debug the workflow

Before coming up with a workflow that runs perfectly in the cloud, you may need to debug it. With `dstack`, you can debug
your workflow right in the cloud using an IDE. One way to do this is by using
the [`code`](../reference/providers/code.md) provider.

Define the following workflow:

<div editor-title=".dstack/workflows/dolly.yaml"> 

```yaml
workflows:
  - name: debug-dolly
    provider: code
    ports: 1
    setup:
      - pip install -r tutorials/dolly/requirements.txt
    cache:
      - ~/.cache/pip
    resources:
      gpu:
        name: A100
      memory: 60GB
      interruptible: true
```

</div>

If you run it, `dstack` will run a VS Code application with the code, dependencies, and hardware resources
you've specified.

<div class="termy">

```shell
$ dstack run debug-dolly --remote

RUN        WORKFLOW     SUBMITTED  STATUS     TAG  BACKENDS
mangust-1  debug-dolly  now        Submitted       gcp

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

The PORT_0 port is mapped to http://0.0.0.0:51742

Web UI available at http://127.0.0.1:51741
```

</div>

Clicking the last link will open VS Code on the provisioned machine.

![](dstack-dolly-code.png)

You can run your code interactively, debug it, and run the application there.
After fixing the workflow, you can run it using the `bash` provider.

!!! info "NOTE:"
    If you omit the `--remote` flag in your `dstack run` command, the workflow will run locally on your machine. Although you
    may not have the required hardware resources, it's a good way to quickly test your workflow before running it in the
    cloud.

As an alternative to the `code` provider, you can run the `bash` provider with `ssh` set to `true`. This allows you to attach
your own IDE to the running workflow.

## 6. Conclusion

When should I use `dstack`? Firstly, when you want to easily run ML workflows, provision cloud resources on-demand, and
keep your project reproducible and easy to collaborate on. Secondly, when you want to run batch workflows in the cloud
on-demand. In the case of Dolly, this could be a batch job that processes specific data.