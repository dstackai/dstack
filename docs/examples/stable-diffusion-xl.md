# Serving SDXL with FastAPI

Stable Diffusion XL (SDXL) 1.0 is the latest version of the open-source model that is capable 
of generating high-quality images from text.

This example demonstrates how to use `dstack` to serve SDXL as a REST endpoint in a cloud of your choice for image
generation and refinement.

## Defining endpoints

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

However, since SDXL allows refining images, let's define the refine endpoint to accept the image ID and the refinement prompt.

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

The code for the endpoints is ready. Now, let's explore how to use dstack to serve it on a cloud account of your choice.

## Defining a profile

!!! info "NOTE:"
    Before using `dstack` with a particular cloud, make sure to [configure](../docs/guides/projects.md) the corresponding project.

SDXL requires at least `12GB` of GPU memory and at least `16GB` of RAM. 
To inform `dstack` about the required resources, you need to 
[define](../docs/reference/profiles.yml.md) a profile via the `.dstack/profiles.yaml` file within your project:

<div editor-title=".dstack/profiles.yml"> 

```yaml
profiles:
  - name: gcp-sdxl
    project: gcp
    resources:
      memory: 16GB
      gpu:
        memory: 12GB
    default: true
```

</div>

## Serving endpoints

Here's the configuration that serves our endpoints via `dstack`:

<div editor-title="stable-diffusion-xl/api.dstack.yml"> 

```yaml
type: task

ports:
 - 8000

commands: 
  - pip install -r stable-diffusion-xl/requirements.txt
  - uvicorn stable-diffusion-xl.main:app --port 8000
```

</div>

Here's how you run it with `dstack`:

<div class="termy">

```shell
$ dstack run . -f stable-diffusion-xl/api.dstack.yml --ports 8000:8000
```

</div>

`dstack` will provision the cloud instance, run the task, and forward the defined ports to your local
machine for secure and convenient access.

Now, you can query the endpoints:

<div class="termy">

```shell
$ curl -X POST --location http://127.0.0.1:8000/generate \
    -H 'Content-Type: application/json' \
    -d '{ "prompt": "A cat in a hat" }'
```

</div>

For more details on SDXL, check its [documentation](https://huggingface.co/docs/diffusers/api/pipelines/stable_diffusion/stable_diffusion_xl) on Hugging Face's website.

[Source code](https://github.com/dstackai/dstack-examples){ .md-button .md-button--github }