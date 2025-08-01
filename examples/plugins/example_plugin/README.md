## Overview

This is a basic `dstack` plugin example.
You can use it as a reference point when implementing new `dstack` plugins.

## Steps

1. Init the plugin package:

    ```
    uv init --library
    ```

2. Define `ApplyPolicy` and `Plugin` subclasses:

    ```python
    from dstack.plugins import ApplyPolicy, Plugin, RunSpec, get_plugin_logger


    logger = get_plugin_logger(__name__)


    class ExamplePolicy(ApplyPolicy):

        def on_run_apply(self, user: str, project: str, spec: RunSpec) -> RunSpec:
            # ...
            return spec


    class ExamplePlugin(Plugin):
        
        def get_apply_policies(self) -> list[ApplyPolicy]:
            return [ExamplePolicy()]

    ```

3. Specify a "dstack.plugins" entry point in `pyproject.toml`:

    ```toml
    [project.entry-points."dstack.plugins"]
    example_plugin = "example_plugin:ExamplePlugin"
    ```

4. Make sure to install the plugin and enable it in the `server/config.yml`:

    ```yaml
    plugins:
    - example_plugin
    projects:
    - name: main
      # ...
    ```
