# dstack run

This command runs a given configuration.

<div class="termy">

```shell
$ dstack run . --help
#GENERATE#
```

</div>

??? info ".gitignore"
    When running dev environments or tasks, `dstack` uses the exact version of code that is present in the folder where you
    use the `dstack run` command.

    If your folder has large files or folders, this may affect the performance of the `dstack run` command. To avoid this,
    make sure to create a `.gitignore` file and include these large files or folders that you don't want to include when
    running dev environments or tasks.