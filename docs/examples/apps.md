# Apps

Both the [`bash`](../reference/providers/bash.md) and [`docker`](../reference/providers/docker.md) providers 
allow to host applications.

To do that, you have to use the `ports` property to specify the number of ports to expose.

The exact port numbers will be passes to the workflow via environment variables `PORT_0`, `PORT_1`, 
etc.

Note, make sure to use the `0.0.0.0` as the hostname.

This workflow launches a FastAPI application.

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: hello-fastapi
        provider: bash
        ports: 1
        commands:
          - pip install fastapi uvicorn
          - uvicorn hello_fastapi:app --port $PORT_0 --host 0.0.0.0
    ```

=== "hello_fastapi.py"

    ```python
       from fastapi import FastAPI
       
       app = FastAPI()
       
       
       @app.get("/")
       async def root():
           return {"message": "Hello World"}
    ```