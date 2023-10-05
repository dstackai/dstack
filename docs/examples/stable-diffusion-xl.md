# Serving SDXL with FastAPI

Stable Diffusion XL (SDXL) 1.0 is the latest version of the open-source model that is capable 
of generating high-quality images from text.

The example below demonstrates how to use `dstack` to serve SDXL as a REST endpoint in a cloud of your choice for image
generation and refinement.

## Define endpoints

### Requirements

Here's the list of libraries that our example will require:

<div editor-title="text-generation-inference/requirements.txt">

```text
transformers
accelerate
safetensors
diffusers
invisible-watermark>=0.2.0
opencv-python-headless
fastapi
uvicorn
```

</div>

Let's walk through the code of the example.

### Load the model

First of all, let's load the base SDXL model using the `diffusers` library.

```python
from diffusers import StableDiffusionXLPipeline
import torch


base = StableDiffusionXLPipeline.from_pretrained(
    "stabilityai/stable-diffusion-xl-base-1.0",
    torch_dtype=torch.float16,
    variant="fp16",
    use_safetensors=True,
)
base.to("cuda")
```

### Define the generate endpoint

Now that the model is loaded, let's define the FastAPI app and the `/generate` REST endpoint that will accept a prompt and
generate an image.

```python
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class GenerateRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = None
    width: Optional[int] = None
    height: Optional[str] = None


class ImageResponse(BaseModel):
    id: str


images_dir = Path("images")
images_dir.mkdir(exist_ok=True)


@app.post("/generate")
async def generate(request: GenerateRequest):
    image = base(
        prompt=request.prompt,
        negative_prompt=request.negative_prompt,
        width=request.width,
        height=request.height,
    ).images[0]
    id = str(uuid.uuid4())
    image.save(images_dir / f"{id}.png")
    return ImageResponse(id=id)
```

### Define the download endpoint

Notice that the endpoint only returns the ID of the image. To download images by ID, we'll define another endpoint:

```python
from fastapi.responses import FileResponse


@app.get("/download/{id}")
def download(id: str):
    filename = f"{id}.png"
    return FileResponse(
        images_dir / filename, media_type="image/png", filename=filename
    )
```

That's it. Once we run the application, we can already utilize the `/generate` and `/download` endpoints.

### Define the refine endpoint

Since SDXL allows refining images, let's define the refine endpoint to accept the image ID and the refinement prompt.

```python
import asyncio

import PIL


class RefineRequest(BaseModel):
    id: str
    prompt: str


refiner = None
refiner_lock = asyncio.Lock()


@app.post("/refine")
async def refine(request: RefineRequest):
    await refiner_lock.acquire()
    global refiner
    if refiner is None:
        refiner = DiffusionPipeline.from_pretrained(
            "stabilityai/stable-diffusion-xl-refiner-1.0",
            text_encoder_2=base.text_encoder_2,
            vae=base.vae,
            torch_dtype=torch.float16,
            use_safetensors=True,
            variant="fp16",
        )
        refiner.to("cuda")
    refiner_lock.release()

    image = refiner(
        prompt=request.prompt,
        image=PIL.Image.open(images_dir / f"{request.id}.png"),
    ).images[0]

    id = str(uuid.uuid4())
    image.save(images_dir / f"{id}.png")
    return ImageResponse(id=id)
```

The code for the endpoints is ready. Now, let's explore how to use `dstack` to serve it on a cloud account of your choice.

## Define the configuration

??? info "Tasks"
    If you want to serve an application for development purposes only, you can use 
    [tasks](../docs/guides/services.md). 
    In this scenario, while the application runs in the cloud, 
    it is accessible from your local machine only.

For production purposes, the optimal approach to serve an application is by using 
[services](../docs/guides/services.md). In this case, the application can be accessed through a public endpoint.

Here's the configuration that uses services:

<div editor-title="stable-diffusion-xl/api.dstack.yml"> 

```yaml
type: service

# (Optional) If not specified, it will use your local version
python: "3.11"

port: 8000

commands: 
  - apt-get update 
  - apt-get install libgl1 -y
  - pip install -r stable-diffusion-xl/requirements.txt
  - uvicorn stable-diffusion-xl.main:app --port 8000
```

</div>

## Run the configuration

!!! warning "NOTE:"
    Before running a service, ensure that you have configured a [gateway](../docs/guides/clouds.md#configuring-gateways).

After the gateway is configured, go ahead run the service.

<div class="termy">

```shell
$ dstack run . -f stable-diffusion-xl/api.dstack.yml
```

</div>

!!! info "Endpoint URL"
    If you've configured a [wildcard domain](../docs/guides/clouds.md#configuring-gateways) for the gateway, 
    `dstack` enables HTTPS automatically and serves the service at 
    `https://<run name>.<your domain name>`.

    If you wish to customize the run name, you can use the `-n` argument with the `dstack run` command.

Once the service is up, you can query the endpoint:

<div class="termy">

```shell
$ curl -X POST --location https://yellow-cat-1.mydomain.com/generate \
    -H 'Content-Type: application/json' \
    -d '{ "prompt": "A cat in a hat" }'
```

</div>

[Source code](https://github.com/dstackai/dstack-examples){ .md-button .md-button--github }