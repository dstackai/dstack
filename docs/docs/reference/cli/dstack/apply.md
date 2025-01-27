# dstack apply

This command applies a given configuration. If a resource does not exist, `dstack apply` creates the resource.
If a resource exists, `dstack apply` updates the resource in-place or re-creates the resource if the update is not possible.

When applying run configurations, `dstack apply` requires that you run `dstack init` first,
or specify a repo to work with via `-P` (or `--repo`), or specify `--no-repo` if you don't need any repo for the run.

## Usage

<div class="termy">

```shell
$ dstack apply --help
#GENERATE#
```

</div>

[//]: # (TODO: Provide examples)
