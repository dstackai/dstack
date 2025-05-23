## Overview

If you wish to hook up your own plugin server through `dstack` builtin `rest_plugin`, here's a basic example on how to do so.

## Steps


1. Install required dependencies for the plugin server:

    ```bash
    uv sync 
    ```

1. Start the plugin server locally:

    ```bash
    fastapi dev app/main.py 
    ```

1. Enable `rest_plugin` in `server/config.yaml`:

    ```yaml
   plugins:
    - rest_plugin
    ```

1. Point the `dstack` server to your plugin server:
    ```bash
    export DSTACK_PLUGIN_SERVICE_URI=http://127.0.0.1:8000
    ```
