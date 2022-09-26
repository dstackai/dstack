# dstack init

This command authorizes dstack to use the current Git credentials (to fetch your code when running workflows).
Not needed for public repos.

### Usage

```shell
dstack init [-t GITHUB_TOKEN | -i SSH_PRIVATE_KEY]
```

!!! info "NOTE:"
    The credentials are stored in the encrypted cloud storage (e.g. for AWS, it's Secrets Manager).

#### Arguments reference

The following arguments are optional:

- `-t GITHUB_TOKEN`, `--token GITHUB_TOKEN` - (Optional) An authentication token for GitHub
- `-i SSH_PRIVATE_KEY`, `--identity SSH_PRIVATE_KEY` – A path to the private SSH key file 

If no arguments are provided, dstack takes the credentials configured in
    `~/.config/gh/hosts.yml` or `./.ssh/config` for the current Git repo.

!!! info "NOTE:"
    Currently `dstack` supports only Git repos that are hosted on GitHub.