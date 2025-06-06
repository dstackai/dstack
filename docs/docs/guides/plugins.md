# Plugins

The `dstack` plugin system allows extending `dstack` server functionality using external Python packages.

!!! info "Experimental"
    Plugins are currently an _experimental_ feature.
    Backward compatibility is not guaranteed across releases.

## Enable plugins

To enable a plugin, list it under `plugins` in [`server/config.yml`](../reference/server/config.yml.md):

<div editor-title="server/config.yml"> 

```yaml
plugins:
  - my_dstack_plugin
  - some_other_plugin
projects:
- name: main
```

</div>

On the next server restart, you should see a log message indicating that the plugin is loaded.

## Create plugins

To create a plugin, create a Python package that implements a subclass of
`dstack.plugins.Plugin` and exports this subclass as a "dstack.plugins" entry point.

1. Init the plugin package:

    <div class="termy">

    ```shell
    $ uv init --library
    ```

    </div>

2. Define `ApplyPolicy` and `Plugin` subclasses:

    <div editor-title="src/example_plugin/__init__.py"> 

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

    </div>

3. Specify a "dstack.plugins" entry point in `pyproject.toml`:

    <div editor-title="pyproject.toml"> 

    ```toml
    [project.entry-points."dstack.plugins"]
    example_plugin = "example_plugin:ExamplePlugin"
    ```

    </div>

Then you can install the plugin package into your Python environment and enable it via `server/config.yml`.

??? info "Plugins in Docker"
    If you deploy `dstack` using a Docker image you can add plugins either
    by including them in your custom image built upon the `dstack` server image,
    or by mounting installed plugins as volumes.

## Apply policies

Currently the only plugin functionality is apply policies.
Apply policies allow modifying specs of runs, fleets, volumes, and gateways submitted on `dstack apply`.
Subclass `dstack.plugins.ApplyPolicy` to implement them.

Here's an example of how to enforce certain rules using apply policies:

<div editor-title="src/example_plugin/__init__.py"> 

```python
class ExamplePolicy(ApplyPolicy):
    def on_run_apply(self, user: str, project: str, spec: RunSpec) -> RunSpec:
        # Forcing some limits
        spec.configuration.max_price = 2.0
        spec.configuration.max_duration = "1d"
        # Setting some extra tags
        if spec.configuration.tags is None:
            spec.configuration.tags = {}
        spec.configuration.tags |= {
            "team": "my_team",
        }
        # Forbid something
        if spec.configuration.privileged:
            logger.warning("User %s tries to run privileged containers", user)
            raise ValueError("Running privileged containers is forbidden")
        # Set some service-specific properties
        if isinstance(spec.configuration, Service):  
            spec.configuration.https = True
        return spec
```

</div>

## Built-in Plugins

### REST Plugin

`rest_plugin` is a builtin `dstack` plugin that allows writing your custom plugins as API servers, so you don't need to install plugins as Python packages.

Plugins implemented as API servers have advantages over plugins implemented as Python packages in some cases:

* No dependency conflicts with `dstack`.
* You can use any programming language.
* If you run the `dstack` server via Docker, you don't need to extend the `dstack` server image with plugins or map them via volumes.

To get started, check out the [plugin server example](https://github.com/dstackai/dstack/tree/master/examples/plugins/example_plugin_server). The `rest_plugin` server API is documented [here](../reference/plugins/rest_plugin/index.md).
