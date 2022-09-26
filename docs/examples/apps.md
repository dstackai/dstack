# Apps

The [`bash`](../reference/providers/bash.md) and [`docker`](../reference/providers/docker.md) providers 
allow workflows to host applications.

To do that, you have to pass the number of ports (that you want to expose) to the `ports` property.

Here's a workflow that launches a FastAPI application.

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

!!! info "NOTE:"
    The actual port numbers will be passes to the workflow via environment variables `PORT_0`, `PORT_1`, 
    etc.
    
    Don't forget to use `0.0.0.0` as the hostname.