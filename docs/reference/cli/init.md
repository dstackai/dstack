# dstack init

Use this command before you run any workflows within the current Git repository.

This command uploads the current Git credentials to the encrypted cloud storage of secrets. 
dstack uses the these credentials to access the current Git repository when running workflows.

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