# dstack project

Before the CLI can be used, it must be configured with a [project](../../../concepts/projects.md), including a project name, server address, and user token. You can configure multiple projects using the `dstack project` CLI command. The configuration is stored in `~/.dstack/config.yml`.

> The `dstack server` command automatically creates the default `main` project and adds its configuration in `~/.dstack/config.yml`.

The `dstack project set-default` command can be used to switch between multiple projects.

## dstack project add

This command adds a new project configuration.

<div class="termy">

```shell
$ dstack project add --help
#GENERATE#
```

</div>

You can find the command on the project’s settings page:

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-projects-project-cli-v2.png" width="750px" />

## dstack project list

This command lists the projects configured on the client.

<div class="termy">

```shell
$ dstack project list --help
#GENERATE#
```

</div>

## dstack project set-default

This command sets the given project as default.

<div class="termy">

```shell
$ dstack project set-default --help
#GENERATE#
```

</div>

## dstack project delete

This command deletes the given project configuration.

<div class="termy">

```shell
$ dstack project delete --help
#GENERATE#
```

</div>
