---
title: Exports
description: Exporting resources across projects
---

# Exports

Exports allow making resources from one project available to other projects. When a project exports a resource,
the specified importer projects can see and use it as if it were their own.

!!! warning "Experimental"
    Exports are an experimental feature.
    Currently, only [SSH fleets](fleets.md#ssh-fleets) can be exported.

An export is created in the exporter project and specifies the resources to export and the
importer projects that will gain access to them.

Once an export is created, the importer projects can see the exported resources in their resource lists and use them
for running tasks, dev environments, and services. Imported resources appear with a project prefix
(e.g., `team-a/my-fleet`) to distinguish them from the project's own resources.

!!! info "Required project role"
    The user creating or updating an export must have the project admin role on both the exporter project and
    any importer project they add. Alternatively, a global admin can add any project as an importer.

## Manage exports

### Create exports

Use the `dstack export create` command to create a new export. Specify the fleets to export
with `--fleet` and the importer projects with `--importer`:

<div class="termy">

```shell
$ dstack export create my-export --fleet my-fleet --importer team-b
 NAME        FLEETS    IMPORTERS
 my-export   my-fleet  team-b

```

</div>

Both `--fleet` and `--importer` can be specified multiple times:

<div class="termy">

```shell
$ dstack export create shared-gpus --fleet gpu-fleet-1 --fleet gpu-fleet-2 --importer team-b --importer team-c
 NAME         FLEETS                    IMPORTERS
 shared-gpus  gpu-fleet-1, gpu-fleet-2  team-b, team-c

```

</div>

### List exports

Use `dstack export list` (or simply `dstack export`) to list all exports in the project:

<div class="termy">

```shell
$ dstack export list
 NAME         FLEETS                    IMPORTERS
 my-export    my-fleet                  team-b
 shared-gpus  gpu-fleet-1, gpu-fleet-2  team-b, team-c

```

</div>

### Update exports

Use the `dstack export update` command to add or remove fleets and importers from an existing export:

<div class="termy">

```shell
$ dstack export update my-export --add-fleet another-fleet --add-importer team-c
 NAME        FLEETS                   IMPORTERS
 my-export   my-fleet, another-fleet  team-b, team-c

```

</div>

To remove a fleet or importer:

<div class="termy">

```shell
$ dstack export update my-export --remove-importer team-b
 NAME        FLEETS                   IMPORTERS
 my-export   my-fleet, another-fleet  team-c

```

</div>

### Delete exports

Use the `dstack export delete` command to delete an export. This revokes access for all importer projects:

<div class="termy">

```shell
$ dstack export delete my-export
Delete the export my-export? [y/n]: y
Export my-export deleted
```

</div>

Use `-y` to skip the confirmation prompt.

## Access imported fleets

From the importer project's perspective, use `dstack import list` (or simply `dstack import`) to list all imports in the project — i.e., all exports from other projects that this project has been granted access to:

<div class="termy">

```shell
$ dstack import list
 NAME              FLEETS
 team-a/my-export  my-fleet, another-fleet

```

</div>

Imported fleets also appear in `dstack fleet list` in the `<project>/<fleet>` format:

<div class="termy">

```shell
$ dstack fleet list
 NAME                  NODES  GPU          SPOT  BACKEND  PRICE  STATUS  CREATED
 my-local-fleet        1      -            -     ssh      -      active  3 days ago
 team-a/my-fleet       2      A100:80GB:8  -     ssh      -      active  1 week ago
 team-a/another-fleet  1      H100:80GB:4  -     ssh      -      active  2 days ago

```

</div>

Imported fleets can be used for runs just like the project's own fleets.

!!! info "Tenant isolation"
    Exported fleets share the same access model as regular fleets. See [Tenant isolation](fleets.md#tenant-isolation) for details.

!!! info "What's next?"
    1. Check the [`dstack export` CLI reference](../reference/cli/dstack/export.md)
    1. Check the [`dstack import` CLI reference](../reference/cli/dstack/import.md)
    1. Learn how to manage [fleets](fleets.md)
    1. Read about [projects](projects.md) and project roles
