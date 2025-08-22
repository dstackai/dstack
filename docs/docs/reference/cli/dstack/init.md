# dstack init

This command initializes the current directory as a `dstack` [repo](../../../concepts/repos.md).
The directory must be a cloned Git repository.

**Git credentials**

`dstack init` ensures that `dstack` can access a remote Git repository.
By default, the command uses the user's default Git credentials. These can be overridden with
`--git-identity` (private SSH key) or `--token` (OAuth token).

<div class="termy">

```shell
$ dstack init --help
#GENERATE#
```

</div>
