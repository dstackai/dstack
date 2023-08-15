# dstack gateway

Gateway makes running jobs (`type: service`) accessible from the public internet.

!!! info "NOTE:"
    Many domains could be attached to the same gateway. Many jobs could use the same gateway.

## dstack gateway list

The `dstack gateway list` command displays the names and addresses of the gateways configured in the project.

### Usage

<div class="termy">

```shell
$ dstack gateway list
```

</div>

## dstack gateway create

The `dstack gateway create` command creates a new gateway instance in the project.

### Usage

<div class="termy">

```shell
$ dstack gateway create --help     
Usage: dstack gateway create [-h] [--project PROJECT]

Optional Arguments:
  -h, --help         show this help message and exit
  --project PROJECT  The name of the project
  --backend {aws,gcp,azure}
```

</div>

### Arguments reference

The following arguments are optional:

- `--project PROJECT` - (Optional) The name of the project to execute the command for
- `--backend {aws,gcp,azure}` - (Optional) The cloud provider to use for the gateway


## dstack gateway delete

The `dstack gateway delete` command deletes the specified gateway.

### Usage

<div class="termy">

```shell    
$ dstack gateway delete --help
Usage: dstack gateway delete [-h] [--project PROJECT] [-y] NAME

Positional Arguments:
  NAME               The name of the gateway

Optional Arguments:
  -h, --help         show this help message and exit
  --project PROJECT  The name of the project
  -y, --yes          Don't ask for confirmation
```

</div>

### Arguments reference

The following arguments are required:

- `NAME` - (Required) A name of the gateway

The following arguments are optional:

- `--project PROJECT` - (Optional) The name of the project to execute the command for
- `-y`, `--yes` – (Optional) Don't ask for confirmation
