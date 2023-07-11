# .dstack.yml

Configurations are YAML files that describe what you want to run with `dstack`. Configurations can be of two
types: `dev-environment` and `task`.

!!! info "Filename"
    The configuration file must be named with the suffix `.dstack.yml`. For example,
    you can name the configuration file `.dstack.yml` or `app.dstack.yml`. You can define
    these configurations anywhere within your project. 
    
    Each folder may have one default configuration file named `.dstack.yml`.

Below is a full reference of all available properties.

- `type` - (Required) The type of the configurations. Can be `dev-environment` or `task`.
- `image` - (Optional) The name of the Docker image.
- `entrypoint` - (Optional) The Docker entrypoint.
- `build` - (Optional) The list of bash commands to build the environment.
- `ide` - (Required if `type` is `dev-environment`). Can be `vscode`.
- `ports` - (Optional) The list of port numbers to expose.
- `env` - (Optional) The mapping or the list of environment variables (e.g. `PYTHONPATH: src` or `PYTHONPATH=src`).
- `registry_auth` - (Optional) Credentials to pull the private Docker image.
    - `username` - (Required) Username.
    - `password` - (Required) Password or access token.
- `init` - (Optional, only for `dev-environment` type) The list of bash commands to execute on each run.
- `commands` - (Required if `type` is `task`). The list of bash commands to run as a task.
- `python` - (Optional) The major version of Python to pre-install (e.g., `"3.11"`). Defaults to the current version installed locally. Mutually exclusive with `image`. 
- `cache` - (Optional) The directories to be cached between runs.

[//]: # (- `home_dir` - &#40;Optional&#41; The absolute path to the home directory inside the container)

[//]: # (TODO: `artifacts` aren't documented)

[//]: # (TODO: Add examples)

[//]: # (TODO: Mention here or somewhere else of how it works. What base image is used, how ports are forwarded, etc.)
