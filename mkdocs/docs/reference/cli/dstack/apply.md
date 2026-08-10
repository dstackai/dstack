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

## Preventing implicit run recreation

Use `--no-recreate` when a script should ensure that an exact named run is active without
silently changing, stopping, or replacing an existing run:

```shell
dstack apply -f dev.dstack.yml --no-recreate -y -d
```

The option supports named dev environment, task, and service configurations. It rejects unnamed
runs and non-run configurations, and it is mutually exclusive with `--force`.

If the named run is absent or finished, the command follows the normal apply flow. If the run is
active, the command succeeds as a no-op only when all of the following are true:

- the run is owned by the user requesting the plan;
- the plan requires an in-place update action but the effective run specification has no changes;
- the run is `submitted`, `provisioning`, or `running`.

Any configuration change is rejected, including one that could normally be updated in place.
Recreation actions and runs in `pending` or `terminating` state are also rejected. These failures
happen before the CLI sends a stop or apply request. Stop the run explicitly before applying a
configuration that needs to replace it.

For absent or finished runs, the server still validates that the resource observed by the plan has
not changed before applying it. A concurrent same-name run therefore causes the apply to fail
instead of being overwritten.

## User SSH key

By default, `dstack` uses its own SSH key to attach to runs (`~/.dstack/ssh/id_rsa`).
It is possible to override this key via the `--ssh-identity` argument.

[//]: # (TODO: Provide examples)
