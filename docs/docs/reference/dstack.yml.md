# .dstack.yml

Configurations are YAML files that describe what you want to run with `dstack`. Configurations can be of three
types: `dev-environment`, `task`, and `service`.

!!! info "Filename"
    The configuration file must be named with the suffix `.dstack.yml`. For example,
    you can name the configuration file `.dstack.yml` or `app.dstack.yml`. You can define
    these configurations anywhere within your project. 
    
    Each folder may have one default configuration file named `.dstack.yml`.

Below is a full reference of all available properties.

- `build` - (Optional) The list of bash commands to build the environment.
- `cache` - (Optional) The directories to be cached between runs.
- `commands` - (Required if `type` is `task`). The list of bash commands to run as a task.
- `entrypoint` - (Optional) The Docker entrypoint.
- `env` - (Optional) The mapping or the list of environment variables (e.g. `PYTHONPATH: src` or `PYTHONPATH=src`).
- `gateway` - (Required if `type` is `service`) Gateway IP address or domain name.
- `ide` - (Required if `type` is `dev-environment`). Can be `vscode`.
- `image` - (Optional) The name of the Docker image.
- `init` - (Optional, only for `dev-environment` type) The list of bash commands to execute on each run.
- `port` - (Required) The service port to expose (only for `service`)
- `ports` - (Optional) The list of port numbers to expose (only for `dev-environment` and `task`).
- `python` - (Optional) The major version of Python to pre-install (e.g., `"3.11"`). Defaults to the current version installed locally. Mutually exclusive with `image`. 
- `registry_auth` - (Optional) Credentials to pull the private Docker image.
    - `password` - (Required) Password or access token.
    - `username` - (Required) Username.
- `type` - (Required) The type of the configurations. Can be `dev-environment`, `task`, or `service`.

[//]: # (- `home_dir` - &#40;Optional&#41; The absolute path to the home directory inside the container)

[//]: # (TODO: `artifacts` aren't documented)

[//]: # (TODO: Add examples)

[//]: # (TODO: Mention here or somewhere else of how it works. What base image is used, how ports are forwarded, etc.)
