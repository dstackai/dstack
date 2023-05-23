# Apps

!!! info "NOTE:"
    The source code of this example is available in the <a href="https://github.com/dstackai/dstack-playground#readme" target="__blank">Playground</a>. 

Both the [`bash`](../reference/providers/bash.md) and [`docker`](../reference/providers/docker.md) providers 
allow workflows to host applications. To host apps within a workflow, you have to request the list of ports that your apps need. 
Use the `ports` property for that.

Create a Python script with a FastAPI application:

<div editor-title="usage/apps/hello_fastapi.py"> 

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

```yaml
workflows:
  - name: hello-fastapi
    provider: bash
    ports:
      - 3000
    commands:
      - pip install fastapi uvicorn
      - uvicorn usage.apps.hello_fastapi:app --port 3000 --host 0.0.0.0
```

</div>


!!! info "NOTE:" 
    Don't forget to bind your application to the `0.0.0.0` hostname.

If you're running the workflow in the cloud, the `dstack run` command automatically forwards the defined ports from the
remote machine to your local machine.

<div class="termy">
 
```shell
$ dstack run hello-fastapi
 RUN           WORKFLOW       SUBMITTED  STATUS     TAG  BACKENDS
 silly-dodo-1  hello-fastapi  now        Submitted       aws

Starting SSH tunnel...

To interrupt, press Ctrl+C.

INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:63475 (Press CTRL+C to quit)
```
 
 </div>

This allows you to securely access applications running remotely from your local machine.