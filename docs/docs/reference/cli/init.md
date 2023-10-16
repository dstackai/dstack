# dstack init

This command initializes the current folder as a repo.

### Usage

<div class="termy">

```shell
$ dstack init --help
#GENERATE#
```

</div>

### Git credentials

If the current folder is a Git repo, the command authorizes `dstack` to access it.
By default, the command uses the default Git credentials configured for the repo. 
You can override these credentials via `--token` (OAuth token) or `--git-identity`.

### Custom SSH key

By default, this command generates an SSH key that will be used for port forwarding and SSH access to running workloads. 
You can override this key via `--ssh-identity`.