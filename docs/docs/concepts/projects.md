# Projects

Projects enable the isolation of different teams and their resources. Each project can configure its own backends and
control which users have access to it.

## User roles

Each user may be assigned a global role as well as a role within a project.

### Global admin

A user can be assigned or unassigned a global admin role on the user account settings page. This can only be done by 
another global admin.

![](https://github.com/dstackai/static-assets/blob/main/static-assets/images/dstack-projects-global-admin.png?raw=true)

The global admin role allows a user to manage all projects and users.

### Project roles

A user can be added to a project and assigned or unassigned as a project admin on the project settings page.

![](https://github.com/dstackai/static-assets/blob/main/static-assets/images/dstack-projects-project-admin.png?raw=true)

* **Project admin** – The project admin role allows a user to manage the project's settings, including backends and
  members.
* **Project user** – A user added to the project without the admin role can manage its resources, including runs,
  fleets, gateways, and volumes.

## Users

Once created, a user is issued a token. This token can be found on the user account settings page. 

![](https://github.com/dstackai/static-assets/blob/main/static-assets/images/dstack-projects-user-token.png?raw=true)

The token must be used for authentication when logging into the control plane
and when using the CLI or API.