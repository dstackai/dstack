# type: dev-environment (.dstack.yml)

Dev environment allows connecting to a remote virtual machine from VS Code Desktop.

!!! info "Filename"
    The configuration file must be named with the suffix `.dstack.yml`. For example,
    you can name the configuration file `.dstack.yml` or `dev.dstack.yml`. You can define
    these configurations anywhere within your project. 
    
    Each folder may have one default configuration file named `.dstack.yml`.

## Runtime properties:

- `ide` - The IDE to run. Currently only `vscode` is supported.
- `env` - (Optional) The list or mapping of environment variables. Interpolation `PATH=/bin/my:$PATH` is supported. 
- `ports` - (Optional) The list of exposed ports or mappings. Allowed formats:
    - `8000` - expose port `8000` and run the ssh tunnel locally on the same port.
    - `3333:8000` - expose port `8000` and run ssh tunnel locally on port `3333`.
    - `*:8000` - expose port `8000` and run the ssh tunnel locally on the first available port starting from `8000`.
- `python` - (Optional) The preinstalled major python version (from `3.7` to `3.11`). Mutually exclusive with `image` property.
- `setup` - (Optional) The list of commands to be executed once for the environment.
- `init` - (Optional) The list of commands to be executed every restart of the environment.

## Custom docker image properties:

- `image` - (Optional) The docker image. Mutually exclusive with `python` property.
- `entrypoint` - (Optional) The docker entry point to interpret the commands (typically `/bin/bash -i -c`).
- `registry_auth` - (Optional) The credentials to pull the image from the private registry.
    - `username` - The username. Supports secrets interpolation `${{ secrets.GHCR_USER }}`.
    - `password` - The password or token. Supports secrets interpolation `${{ secrets.GHCR_TOKEN }}`.
- `home_dir` - (Optional) The home directory inside the container. Defaults to `/root`.

!!! info "Requirements"
    Custom docker image must have `sshd`.
    You could pre-install `openssh-server` in your `Dockerfile` or use the `build` property.

## Optimization properties:

- `cache` - (Optional) The list of directories to cache between the environment restarts. Both absolute and relative paths are supported.
- `build` - (Optional) The list of commands to run during the build stage. You must call `dstack build` first or use the flag `dstack run --build`.

!!! info "Note"
    The build is an experimental feature. Performance gain depends on the type of workload and specific cloud provider.

## Examples:

### Minimal configuration

```yaml
type: dev-environment
ide: vscode
```

### Custom docker image

```yaml
type: dev-environment
ide: vscode
image: ghcr.io/huggingface/text-generation-inference:latest
build:
  - apt-get update
  - DEBIAN_FRONTEND=noninteractive apt-get install -y openssh-server
  - rm -rf /var/lib/apt/lists/*
env:
  - MODEL_ID=meta-llama/Llama-2-7b-chat-hf
  - HOSTNAME=0.0.0.0
  - PORT=8080
  # HUGGING_FACE_HUB_TOKEN is stored in secrets
ports:
  - 8080
```

[//]: # (TODO: describe profile policies defaults)

[//]: # (TODO: Add examples)

[//]: # (TODO: Mention here or somewhere else of how it works. What base image is used, how ports are forwarded, etc.)

## Schema reference

#SCHEMA# dstack._internal.core.models.configurations.DevEnvironmentConfiguration
    overrides:
      type:
        required: true
