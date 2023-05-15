# dstack init

This command authorizes `dstack` to use the current Git credentials (to fetch your code when running workflows).
Not needed for public repos.

## Usage

<div class="termy">

```shell
$ dstack init --help
Usage: dstack init [-h] [--project PROJECT] [-t OAUTH_TOKEN] [--git-identity SSH_PRIVATE_KEY] [--ssh-identity SSH_PRIVATE_KEY] [--local]

Options:
  --project PROJECT     The Hub project to execute the command for
  -t, --token OAUTH_TOKEN
                        An authentication token for Git
  --git-identity SSH_PRIVATE_KEY
                        A path to the private SSH key file for non-public repositories
  --ssh-identity SSH_PRIVATE_KEY
                        A path to the private SSH key file for SSH tunneling
```

</div>

!!! info "NOTE:"
    If the project runs workflows in the cloud (AWS or GCP), the credentials are stored in the encrypted cloud storage (Secrets Manager).

### Arguments reference

The following arguments are optional:

- `-project PROJECT` – (Optional) The Hub project to execute the command for
- `-t OAUTH_TOKEN`, `--token OAUTH_TOKEN` – (Optional) An authentication token for GitHub
- `--git-identity SSH_PRIVATE_KEY` – (Optional) A path to the private SSH key file for non-public repositories
- `--ssh-identity SSH_PRIVATE_KEY` – (Optional) A path to the private SSH key file for SSH tunneling 

!!! info "NOTE:"
    If no arguments are provided, `dstack` uses the credentials configured in
    `~/.config/gh/hosts.yml` or `./.ssh/config` for the current Git repo.
