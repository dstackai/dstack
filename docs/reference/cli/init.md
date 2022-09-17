# init

The `init` command authorizes dstack to access the current Git repository. 
Use this command on a Git repository before running any workflows in it.

This commands uploads the Git credentials to the cloud storage of credentials within the configured backend 
(for AWS, it's Secrets Manager). 

### Usage

```shell
dstack init [-t TOKEN] [-i FILE]
```

#### Arguments reference

The following arguments are optional:

- `-t GH_TOKEN`, `--token GH_TOKEN` - (Optional) An authentication token for GitHub
- `-i FILE`, `--identity FILE` – A path to the private SSH key file 

!!! warning "NOTE:"
    If no arguments are provided, the command will try to the credentials configured in
    `~/.config/gh/hosts.yml`, `./.ssh/config` for the hostname of the current GitHub repository.

    For public repositories, credentials are not needed.