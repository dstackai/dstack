# dstack init

If you’re using private Git repos in your runs via [`repos`](../../../concepts/dev-environments.md#repos),
`dstack` will automatically try to use your default Git credentials (from
`~/.ssh/config` or `~/.config/gh/hosts.yml`). 

To provide custom Git credentials, run `dstack init`. 

<div class="termy">

```shell
$ dstack init --help
#GENERATE#
```

</div>

You can set credentials with  `--git-identity` (private SSH key) or `--token` (OAuth token).

Run `dstack init` in the repo’s directory, or pass the repo path or URL with `--repo` (or `-P`).
