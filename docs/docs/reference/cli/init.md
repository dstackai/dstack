# dstack init

This command authorizes `dstack` to use the current Git credentials (to fetch your code when running workflows).
Not needed for public repos.

## Usage

<div class="termy">

```shell
$ dstack init --help
Usage: dstack init [-h] [-t OAUTH_TOKEN] [-i SSH_PRIVATE_KEY]

Optional Arguments:
  -h, --help            Show this help message and exit
  -t, --token OAUTH_TOKEN
                        An authentication token for Git
  -i, --identity SSH_PRIVATE_KEY
                        A path to the private SSH key file
```

</div>

!!! info "NOTE:"
    The credentials are stored in the encrypted cloud storage (e.g. for AWS, it's Secrets Manager).

### Arguments reference

The following arguments are optional:

- `-t OAUTH_TOKEN`, `--token OAUTH_TOKEN` – (Optional) An authentication token for GitHub
- `-i SSH_PRIVATE_KEY`, `--identity SSH_PRIVATE_KEY` – (Optional) A path to the private SSH key file 

!!! info "NOTE:"
    If no arguments are provided, `dstack` uses the credentials configured in
    `~/.config/gh/hosts.yml` or `./.ssh/config` for the current Git repo.
