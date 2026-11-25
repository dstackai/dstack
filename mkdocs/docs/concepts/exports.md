---
title: Exports
description: Exporting resources across projects
---

# Exports

Exports allow making resources from one project available to other projects. When a project exports a resource,
the specified importer projects can see and use it as if it were their own.

> Exports are only supported in [dstack Sky](https://dstack.ai/products/sky/) and [dstack Factory](https://dstack.ai/products/factory/).

An export is created in the exporter project and specifies the resources to export and the
importer projects that will gain access to them.

Once an export is created, the importer projects can see the exported resources in their resource lists and use them
for running tasks, dev environments, and services. Imported fleets and gateways appear with a project prefix
(e.g., `team-a/my-fleet`) to distinguish them from the project's own resources.

Currently, [fleets](fleets.md), [gateways](gateways.md), and [models](services.md#model) can be exported.

??? info "Limitations"
    - [Container-based](backends.md#container-based) backends of the exporter project cannot be used for fleet importers' runs.
    - Runs that mount [network volumes](volumes.md#network-volumes) cannot use imported backend fleets.
    - Models cannot be added to [global exports](#global-exports).
    - Importer projects can access an exported model only if its service uses the `openai` model format (the default) and a [gateway](gateways.md) whose `domain` doesn't include `${{ run.project_name }}`.
    - If the importer project runs a model with the same name on the same gateway, the project's own model is used.

??? info "Required role"
    The user creating or updating an export must have the project admin role on both the exporter project and
    any importer project they add. Alternatively, a global admin can add any project as an importer.

## Manage exports

### Create exports

Use the `dstack export create` command to create a new export. Specify the fleets to export
with `--fleet`, the gateways to export with `--gateway`, the [models](#export-models) to export with `--model`,
and the importer projects with `--importer`:

<div class="termy">

```shell
$ dstack export create my-export --fleet my-fleet --gateway my-gateway --importer team-b
 NAME       FLEETS    GATEWAYS    MODELS  IMPORTERS
 my-export  my-fleet  my-gateway  -       team-b

```

</div>

`--fleet`, `--gateway`, `--model`, and `--importer` can be specified multiple times:

<div class="termy">

```shell
$ dstack export create shared-gpus --fleet gpu-fleet-1 --fleet gpu-fleet-2 --importer team-b --importer team-c
 NAME         FLEETS                    GATEWAYS  MODELS  IMPORTERS
 shared-gpus  gpu-fleet-1, gpu-fleet-2  -         -       team-b, team-c

```

</div>

### List exports

Use `dstack export list` (or simply `dstack export`) to list all exports in the project:

<div class="termy">

```shell
$ dstack export list
 NAME         FLEETS                    GATEWAYS    MODELS  IMPORTERS
 my-export    my-fleet                  my-gateway  -       team-b
 shared-gpus  gpu-fleet-1, gpu-fleet-2  -           -       team-b, team-c

```

</div>

### Update exports

Use the `dstack export update` command to add or remove fleets, gateways, models, and importers from an existing export:

<div class="termy">

```shell
$ dstack export update my-export --add-fleet another-fleet --add-importer team-c
 NAME       FLEETS                   GATEWAYS    MODELS  IMPORTERS
 my-export  my-fleet, another-fleet  my-gateway  -       team-b, team-c

```

</div>

To remove a fleet, gateway, model, or importer:

<div class="termy">

```shell
$ dstack export update my-export --remove-importer team-b
 NAME       FLEETS                   GATEWAYS    MODELS  IMPORTERS
 my-export  my-fleet, another-fleet  my-gateway  -       team-c

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

### Global exports

Users with the global admin role can mark any export as a global export. Global exports are automatically imported into all projects, and their imports cannot be deleted.

<div class="termy">

```shell
$ dstack export create global-export --gateway shared-gateway --global
 NAME           FLEETS  GATEWAYS        MODELS  IMPORTERS
 global-export  -       shared-gateway  -       *

```

</div>

Only promoting an export to global requires the global admin role. Regular project admins can add or remove resources, remove global status, or delete the export.

### Export models

To export a [model](services.md#model), pass the name set in the service's `model` property with `--model`:

<div class="termy">

```shell
$ dstack export create my-models --model Qwen/Qwen3.8-27B-FP8 --importer team-b
 NAME       FLEETS  GATEWAYS  MODELS                IMPORTERS
 my-models  -       -         Qwen/Qwen3.8-27B-FP8  team-b

```

</div>

Models are exported by name, so an export stays in place when the model's service is stopped, replaced, or not started yet.

## Access imported resources

From the importer project's perspective, use `dstack import list` (or simply `dstack import`) to list all imports in the project — i.e., all exports from other projects that this project has been granted access to:

<div class="termy">

```shell
$ dstack import list
 NAME              FLEETS                   GATEWAYS    MODELS
 team-a/my-export  my-fleet, another-fleet  my-gateway  -
 team-a/my-models  -                        -           Qwen/Qwen3.8-27B-FP8

```

</div>

Imported fleets and gateways also appear in `dstack fleet list` and `dstack gateway list` in the `<project>/<name>` format:

<div class="termy">

```shell
$ dstack fleet list
 NAME                  NODES  GPU          SPOT  BACKEND  PRICE  STATUS  CREATED
 my-local-fleet        1      -            -     ssh      -      active  3 days ago
 team-a/my-fleet       2      A100:80GB:8  -     ssh      -      active  1 week ago
 team-a/another-fleet  1      H100:80GB:4  -     ssh      -      active  2 days ago

$ dstack gateway list
 NAME               BACKEND          HOSTNAME  DOMAIN                 DEFAULT  STATUS
 team-a/my-gateway  aws (eu-west-1)  10.0.0.4  gtw.mycompany.example           running

```

</div>

Imported resources can be used for runs just like the project's own resources.

<div editor-title=".dstack.yml">
    
```yaml
type: service
image: nginx
port: 80

gateway: team-a/my-gateway

fleets:
- my-local-fleet
- team-a/my-fleet
```

</div>

### Imported models

Imported models are available at the importer project's [model endpoint](services.md#model). Use `dstack import list -v` to see their URLs:

<div class="termy">

```shell
$ dstack import list -v
 NAME              FLEETS                   GATEWAYS    MODEL                 URL
 team-a/my-export  my-fleet, another-fleet  my-gateway  -
 team-a/my-models  -                        -           Qwen/Qwen3.8-27B-FP8  https://gateway.example.com/team-b

```

</div>

A model has a URL only while its service is running.

!!! info "Tenant isolation"
    Exported fleets share the same access model as regular fleets. See [Tenant isolation](../guides/tenant-isolation.md) for details.

    Requests to imported models, including user tokens, go through the exporter project's gateway.

!!! info "What's next?"
    1. Check the [`dstack export` CLI reference](../reference/cli/dstack/export.md)
    2. Check the [`dstack import` CLI reference](../reference/cli/dstack/import.md)
    3. Learn how to manage [fleets](fleets.md)
    4. Learn how to manage [gateways](gateways.md)
    5. Learn how to run [services](services.md)
    6. Read about [projects](projects.md) and project roles
