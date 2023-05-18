# dstack init

This command initializes the current directory as a repository.

If the current repository is a Git repository, the command authorizes dstack to access it. By default, the command uses
the default Git credentials configured for the repository. You can override these credentials by using arguments.

The command also configures the SSH key that will be used for port forwarding and SSH access to running workflows. By
default, it generates its own key. You can override this key by using the arguments. 

## Usage

<div class="termy">

```shell
$ dstack init --help
Usage: dstack init [-h] [--project PROJECT] [-t OAUTH_TOKEN] [--git-identity SSH_PRIVATE_KEY] [--ssh-identity SSH_PRIVATE_KEY]

Options:
  --project PROJECT     The Hub project to execute the command for
  -t, --token OAUTH_TOKEN
                        An authentication token for Git
  --git-identity SSH_PRIVATE_KEY
                        A path to the private SSH key file for non-public repositories
  --ssh-identity SSH_PRIVATE_KEY
                        A path to the private SSH key file for SSH port forwarding
```

</div>

### Arguments reference

The following arguments are optional:

- `-project PROJECT` – (Optional) The Hub project to execute the command for
- `-t OAUTH_TOKEN`, `--token OAUTH_TOKEN` – (Optional) An authentication token for GitHub
- `--git-identity SSH_PRIVATE_KEY` – (Optional) A path to the private SSH key file for non-public repositories
- `--ssh-identity SSH_PRIVATE_KEY` – (Optional) A path to the private SSH key file for SSH port forwarding 

!!! info "NOTE:"
    If Git credentials are not passed via `--token OAUTH_TOKEN` or `--git-identity SSH_PRIVATE_KEY`, `dstack` uses the credentials configured in
    `~/.config/gh/hosts.yml` or `./.ssh/config` for the current Git repo.

!!! info "NOTE:"
    If the project is configured to use the cloud, the credentials are stored in the encrypted cloud storage.