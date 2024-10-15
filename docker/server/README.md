# `dstack`: Streamlined AI Container Orchestration

`dstack` is a streamlined alternative to Kubernetes, specifically designed for AI workloads. It simplifies container orchestration for AI development, training, and deployment, whether in the cloud or on-prem, helping speed up your AI pipeline.

`dstack` supports `NVIDIA GPU`, `AMD GPU`, and `Google Cloud TPU` out of the box.

## Configuring Backends

To use `dstack` with your cloud accounts, create the `~/.dstack/server/config.yml` file and 
[configure the backends](https://dstack.ai/docs/reference/server/config.yml) accordingly.

## Starting the Server

You can start the `dstack` server using Docker with the following command:

```shell
docker run -p 3000:3000 -v $HOME/.dstack/server/:/root/.dstack/server dstackai/dstack
```

Once running, the server will be accessible at `http://0.0.0.0:3000`.

The admin user token for this instance is:

```
bbae0f28-d3dd-4820-bf61-8f4bb40815da
```

For additional server configuration options, see the
[server deployment guide](https://dstack.ai/docs/guides/server-deployment.md).

## Setting Up the CLI

To configure the CLI to communicate with your `dstack` server, run:

```shell
pip install dstack
dstack config --url http://127.0.0.1:3000 \
    --project main \
    --token bbae0f28-d3dd-4820-bf61-8f4bb40815da
```

The configuration will be updated in `~/.dstack/config.yml`.

## Creating SSH Fleets

To enable the `dstack` server to run containers on your on-prem servers, set up [fleets](https://dstack.ai/docs/concepts/fleets#ssh-fleets).

## More Information

For additional resources and examples, explore the following links:

- [Documentation](https://dstack.ai/docs)
- [Examples](https://dstack.ai/examples)
- [Changelog](https://github.com/dstackai/dstack/releases)
- [Join our Discord](https://discord.gg/u8SmfwPpMd)

## License

`dstack` is licensed under the [Mozilla Public License 2.0](https://github.com/dstackai/dstack/blob/master/LICENSE.md).

---
