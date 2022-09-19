# dstack

The base command for the `dstack` CLI.

## Usage

To view a list of the commands available in your current dstack version, run `dstack` with no additional arguments:

```bash
Usage: dstack [OPTIONS ...] COMMAND [ARGS ...]

Main commands:
  run            Run a workflow
  ps             List runs
  stop           Stop a run
  logs           Show logs of a run
  artifacts      List or download artifacts of a run or a tag
  tags           List, create or delete tags

Other commands:
  init           Authorize dstack to access the current GitHub repo
  config         Configure the backend
  secrets        Manage secrets
  delete         Delete runs

Options:
  -h, --help     Show this help output, or the help for a specified command.
  -v, --version  Show the version of the CLI.
```

To get specific help for any specific command, use the `--help` option with the relevant command. 
For example, to see help about the "init" command you can run `dstack init --help`.

For more detailed information, refer to each command's section of this documentation, available in the navigation 
section of this page.
