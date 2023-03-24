# Apps

!!! info "NOTE:"
    The source code for the examples below can be found on [GitHub](https://github.com/dstackai/dstack-examples).

Both the [`bash`](../reference/providers/bash.md) and [`docker`](../reference/providers/docker.md) providers 
allow workflows to host applications. To host apps within a workflow, you have to request the number of ports that your apps need. 
Use the `ports` property for that.

The actual port numbers will be passes to the workflow via environment variables `PORT_0`, `PORT_1`, etc.

Create a Python script with a FastAPI application:

<div editor-title="apps/hello_fastapi.py"> 

```python
from fastapi import FastAPI

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}
```

</div>

Now, define the following workflow YAML file:

<div editor-title=".dstack/workflows/apps.yaml"> 

```yaml hl_lines="4 7"
workflows:
  - name: hello-fastapi
    provider: bash
    ports: 1
    commands:
      - pip install fastapi uvicorn
      - uvicorn apps.hello_fastapi:app --port $PORT_0 --host 0.0.0.0
```

</div>


!!! info "NOTE:" 
    Don't forget to bind your application to the `0.0.0.0` hostname.