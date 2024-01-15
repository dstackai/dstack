# dstack gateway

## Purpose

* Make dstack services available to the outside world
* Manage SSL certificates
* Manage nginx configs
* Establish SSH tunnels from gateway to dstack runner
* Proxy OpenAI API requests to different formats (e.g. TGI)

## Development

1. Build the wheel:
    ```
    python -m build .
    ```
2. Upload the wheel:
    ```shell
    scp dist/dstack_gateway-0.0.0-py3-none-any.whl ubuntu@${GATEWAY}:/tmp/
    ```
3. Install the wheel:
    ```
    ssh ubuntu@${GATEWAY} "pip install --force-reinstall /tmp/dstack_gateway-0.0.0-py3-none-any.whl"
    ```
4. Run the tunnel and the gateway:
    ```
    ssh -L 9001:localhost:8000 -t ubuntu@${GATEWAY} "uvicorn dstack.gateway.main:app"
    ```
5. Visit the gateway docs page at http://localhost:9001/docs
