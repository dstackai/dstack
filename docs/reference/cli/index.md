# dstack

The base command for the `dstack` CLI.

### Usage

To view the list of supported CLI commands, run `dstack` with no additional arguments:

```bash
Usage: dstack [-h] [-v] [OPTIONS ...] COMMAND [ARGS ...]

Main commands:
  dstack run WORKFLOW [-d] [-l] [-t TAG] [ARGS ...]   Run a workflow
  dstack ps [-a | RUN]                                Show run(s) status
  dstack stop [-x] [-y] (RUN | -a)                    Stop run(s)
  dstack logs [-a] [-s SINCE] RUN                     Show logs of a run
  dstack artifacts list (RUN | :TAG)                  List artifacts
  dstack artifacts download (RUN | :TAG)              Download artifacts

Other commands:
  dstack init [-t OAUTH_TOKEN | -i SSH_PRIVATE_KEY]   Initialize the repo
  dstack config                                       Configure the backend
  dstack tags add TAG (-r RUN | -a PATH ...)          Add a tag
  dstack tags delete [-y] TAG                         Delete a tag
  dstack tags list                                    List tags
  dstack secrets add [-y] NAME [VALUE]                Add a secret
  dstack secrets list                                 List secrets
  dstack secrets delete NAME                          Delete a secret
  dstack rm [-y] (RUN | -a)                           Remove run(s)

Global options:
  -h, --help                                          Show this help output
  -v, --version                                       Show dstack version
```

!!! tip "NOTE:"
    To quickly see the usage of a particular command, use the command name and  `--help` together:
    
    ```shell
     dstack run --help
    ```

For more details and examples on a specific command, check out its dedicate reference page using the navigation section.
