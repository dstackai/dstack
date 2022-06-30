# Run providers

As an alternative to [workflows](workflows), you can run providers directly using the CLI.

!!! info ""    
    To see the entire list of built-in providers, they parameters, and examples, check out the [providers](https://github.com/dstackai/dstack/tree/master/providers#readme) page.

Here's an example: 

```bash
dstack run python train.py \
  --epoch 100 --seed 2 --batch-size 128 \
  --dep prepare:latest --artifact checkpoint --gpu 1 
```

Every provider may have its own list of required and non-required CLI arguments.

!!! info "Git"
    Be sure to invoke the dstack CLI from the repository directory.

    As long as your project is under Git, you don't have to commit local changes before running workflows.
    dstack tracks staged local changes automatically and allows you to see them in the user interface
    for every run.

Once you've run a provider, you'll see it in the user interface. 
To see recent runs from the CLI, use the following command:

```bash
dstack runs
```

[//]: # (TODO: Show a screennshot of repo diff)

[//]: # (TODO: Tell about statuses)

[//]: # (TODO: Tell about availability issues)

[//]: # (TODO: Provide mode provider examples)

### Logs

The output of running providers is tracked in real-time and can be accessed through the user interface
or the CLI.

To access the output through the CLI, use the following command:

```bash
dstack logs <run-name>
```

If you'd like to see the output in real-time through the CLI, add the `-f` (or `--follow`) argument:

```bash
dstack logs <run-name> -f
```

### Artifacts

By default, the output artifacts are tracked in real-time and can be accessed either via the user interface
or the CLI.

To browse artifacts through the CLI, use the following command:

```bash
dstack artifacts list <run-name>
```

To download artifacts locally, use the following command:

```bash
dstack artifacts download <run-name>
```

[//]: # (TODO: Add screenshots)

[//]: # (TODO: Tell about stopping and restarting workflows)

[//]: # (TODO: Add a link to the CLI reference)

[//]: # (TODO: Add a link to Providers Reference)
