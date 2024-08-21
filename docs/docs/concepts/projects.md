# Projects

Projects enable the isolation of different teams and their resources. Each project can configure its own backends and
control which users have access to it.

> While project backends can be configured via [`~/.dstack/server/config.yml`](../reference/server/config.yml.md), use the control plane UI to fully manage
> projects, users, and user permissions.

## Project backends

In addition to [`~/.dstack/server/config.yml`](../reference/server/config.yml.md), 
a global admin or a project admin can configure backends on the project settings page.

<img src="https://github.com/dstackai/static-assets/blob/main/static-assets/images/dstack-projects-project-backends.png?raw=true" width="750px" />

## Global admins

A user can be assigned or unassigned a global admin role on the user account settings page. This can only be done by 
another global admin.

<img src="https://github.com/dstackai/static-assets/blob/main/static-assets/images/dstack-projects-global-admin.png?raw=true" width="750px" />

The global admin role allows a user to manage all projects and users.

## Project members

A user can be added to a project and assigned or unassigned as a project role on the project settings page.

<img src="https://github.com/dstackai/static-assets/blob/main/static-assets/images/dstack-projects-project-admin.png?raw=true" width="750px" />

### Project roles

* **Admin** – The project admin role allows a user to manage the project's settings,
  including backends, gateways, and members.
* **Manager** – The project manager role allows a user to manage project members.
  Unlike admins, managers cannot configure backends and gateways.
* **User** – A user can manage project resources including runs, fleets, and volumes.

## Authorization

### User token

Once created, a user is issued a token. This token can be found on the user account settings page. 

<img src="https://github.com/dstackai/static-assets/blob/main/static-assets/images/dstack-projects-user-token.png?raw=true" width="750px" />

The token must be used for authentication when logging into the control plane UI
and when using the CLI or API.

### Setting up the CLI

To use the CLI with a specific project, run the `dstack config` command with the server address, user token, and project name.

You can find the command on the project’s settings page:

<img src="https://github.com/dstackai/static-assets/blob/main/static-assets/images/dstack-projects-project-cli.png?raw=true" width="750px" />

??? info "API"
    In addition to the UI, managing projects, users, and user permissions can also be done via the [REST API](../reference/api/rest/index.md)).