# Tensorboard

This provider launches a Tensorboard application that visualizes experiment metrics for given runs.

You must specify at least one run name.

## Example usage 

### Basic example

```bash
dstack run tensorboard selfish-wolverine-1
```

## CLI reference

```bash
usage: dstack run tensorboard [-d] [-h] [--logdir LOGDIR] RUN [RUN ...]

positional arguments:

optional arguments:
  -h, --help       show this help message and exit
  --logdir LOGDIR  The path where TensorBoard will look for event files. By default, TensorBoard
                   willscan all run artifacts.
```

The following arguments are required:

- `RUN` – (Required) A name of a run

The following arguments are optional:

- `-d`, `--detach` - (Optional) Do not poll for status update and logs
- `--logdir LOGDIR` - (Optional) The path where TensorBoard will look for event files. By default, TensorBoard
    will scan all run artifacts.

## Source code

[:octicons-arrow-right-24: GitHub](https://github.com/dstackai/dstack/tree/master/src/dstack/providers/tensorboard)