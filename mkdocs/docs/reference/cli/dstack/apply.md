# dstack apply

This command applies a given configuration. If a resource does not exist, `dstack apply` creates the resource.
If a resource exists, `dstack apply` updates the resource in-place or re-creates the resource if the update is not possible.

To mount a Git repo to the run's container, `dstack apply` requires that you run `dstack init` first,
or specify a repo to work with via `-P` (or `--repo`), or specify `--no-repo` if you don't need any repo for the run.

## Usage

<div class="termy">

```shell
$ dstack apply --help
#GENERATE#
```

</div>

## User SSH key

By default, `dstack` uses its own SSH key to attach to runs (`~/.dstack/ssh/id_rsa`).
It is possible to override this key via the `--ssh-identity` argument.

[//]: # (TODO: Provide examples)
