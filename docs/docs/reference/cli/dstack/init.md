# dstack init

This command initializes the current directory as a `dstack` [repo](../../../concepts/repos.md).

**Git credentials**

If the directory is a cloned Git repository, `dstack init` ensures that `dstack` can access it.
By default, the command uses the user's default Git credentials. These can be overridden with 
`--git-identity` (private SSH key) or `--token` (OAuth token).

<div class="termy">

```shell
$ dstack init --help
#GENERATE#
```

</div>

**User SSH key**

By default, `dstack` uses its own SSH key to access instances (`~/.dstack/ssh/id_rsa`). 
It is possible to override this key via the `--ssh-identity` argument.

[//]: # (TODO: Mention that it's optional, provide reference to `dstack apply`)
