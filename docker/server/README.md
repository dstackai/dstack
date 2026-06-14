`dstack` is a streamlined alternative to Kubernetes, specifically designed for AI. It simplifies container orchestration
for AI workloads both in the cloud and on-prem, speeding up the development, training, and deployment of AI models.

`dstack` supports `NVIDIA GPU`, `AMD GPU`, and `Google Cloud TPU` out of the box.

## Configure backends

To use `dstack` with your own cloud accounts, create the `~/.dstack/server/config.yml` file and 
[configure backends](https://dstack.ai/docs/reference/server/config.yml).

## Start the server

Starting the `dstack` server via Docker can be done the following way:

```shell
docker run -p 3000:3000 -v $HOME/.dstack/server/:/root/.dstack/server dstackai/dstack

The dstack server is running at http://0.0.0.0:3000
The admin user token is 'bbae0f28-d3dd-4820-bf61-8f4bb40815da'
```

For more details on server configuration options, see the
[server deployment](https://dstack.ai/docs/guides/server-deployment.md) guide.

### Run with PostgreSQL and the SSH proxy

In production, the `dstack` server is usually run with
[PostgreSQL](https://dstack.ai/docs/guides/server-deployment#postgresql) instead of the default
SQLite, and with the [SSH proxy](https://dstack.ai/docs/guides/server-deployment#ssh-proxy). The
[`docker-compose.yml`](https://github.com/dstackai/dstack/blob/master/docker/server/docker-compose.yml)
runs that combination locally, so you can try or test a production-like server on your own machine.
A full production deployment would also configure external
[logs storage](https://dstack.ai/docs/guides/server-deployment#logs-storage) and
[file storage](https://dstack.ai/docs/guides/server-deployment#file-storage).

```shell
docker compose -f docker/server/docker-compose.yml up
```

This starts PostgreSQL, the `dstack` server at `http://localhost:3000`, and the SSH proxy at
`localhost:30022`. The admin token is printed to the logs (`docker compose logs server`).

To access the server from the CLI, add it as a project with `dstack project add`, using the
admin token from the logs (see [Set up the CLI](#set-up-the-cli) below).

## Set up the CLI

To point the CLI to the `dstack` server, configure it
with the server address, user token, and project name:

```shell
$ pip install dstack
$ dstack project add --name main \
    --url http://127.0.0.1:3000 \
    --token bbae0f28-d3dd-4820-bf61-8f4bb40815da
    
Configuration is updated at ~/.dstack/config.yml
```

## Create SSH fleets
    
If you want the `dstack` server to run containers on your on-prem servers,
use [fleets](https://dstack.ai/docs/concepts/fleets#ssh-fleets).

## More information

For additional information and examples, see the following links:

* [Docs](https://dstack.ai/docs)
* [Examples](https://dstack.ai/examples)
* [Changelog](https://github.com/dstackai/dstack/releases)
* [Discord](https://discord.gg/u8SmfwPpMd)
 
##  License

[Mozilla Public License 2.0](https://github.com/dstackai/dstack/blob/master/LICENSE.md)
