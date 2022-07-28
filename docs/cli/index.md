# CLI

The command line interface to dstack is provided through the `dstack` program (that is installed with the 
[`dstack`](https://pypi.org/project/dstack/) pip package).

!!! info "NOTE:"
    Make sure to always use the CLI from the project repository directory.

## Example usage

To view a list of the commands available in your current dstack version, run `dstack` with no additional arguments:

```bash
Usage: dstack [OPTIONS ...] COMMAND [ARGS ...]

The available commands for execution are listed below.
The primary commands are given first, followed by
less common or more advanced commands.

Main commands:
  run            Run a workflow
  runs           Show recent runs
  stop           Stop a run
  restart        Restart a run
  logs           Show logs of a run
  artifacts      Show or download artifacts of a run
  app            Open a running application

Other commands:
  init           Initialize the repository
  config         Configure your token
  prune          Delete all finished untagged runs
  tag            Assign a tag to a run
  untag          Delete a tag

Options:
  -h, --help     Show this help output, or the help for a specified command.
  -v, --version  Show the version of the CLI.
```

To get specific help for any specific command, use the `--help` option with the relevant command. 
For example, to see help about the "init" command you can run `dstack config --help`.

[//]: # (For more detailed information, refer to each command's section of this documentation, available in the navigation )
[//]: # (section of this page.)

## Installation

Here's how to install and configure the CLI:

```bash
pip install dstack
dstack config --token <token> 
```

Your token can be found on the `Settings` page in the user interface.