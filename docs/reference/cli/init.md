# dstack init

Use this command to authorize dstack to access the current Git repo.

The command uploads the current Git credentials to the encrypted cloud storage (e.g. for AWS, it's Secrets Manager).

The credentials are used by dstack when running workflows to fetch the copy of code.

For public repositories, this command is not needed.

### Usage

```shell
dstack init [-t GITHUB_TOKEN | -i SSH_PRIVATE_KEY_PATH]
```

#### Arguments reference

The following arguments are optional:

- `-t GITHUB_TOKEN`, `--token GITHUB_TOKEN` - (Optional) An authentication token for GitHub
- `-i SSH_PRIVATE_KEY_PATH`, `--identity SSH_PRIVATE_KEY_PATH` – A path to the private SSH key file 

!!! warning "NOTE:"
    If no arguments are provided, the command will try to the credentials configured in
    `~/.config/gh/hosts.yml`, `./.ssh/config` for the hostname of the current GitHub repo.