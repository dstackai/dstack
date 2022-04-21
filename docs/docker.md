# Deploy on-premise

The easiest way to run dstack on-premise is by using its public Docker
image: [`dstackai/dstack`](https://hub.docker.com/r/dstackai/dstack).

!!! info ""
    Note, because dstack runners and CLI have to communicate with the dstack `Server`, the `Server` must be accessible 
    from the network where runners and the CLI are running.

## Docker image

Here's an example on how to quickly run the Docker image:

```bash
docker pull dstackai/dstack
mkdir -p dstack/data
docker run \ 
  -e AWS_ACCESS_KEY_ID=<...> \ 
  -e AWS_SECRET_ACCESS_KEY=<...> \
  -e AWS_DEFAULT_REGION=<...> \ 
  -e DSTACK_ARTIFACTS_S3_BUCKET=<...> \
  -v $(pwd)/dstack/data:/data \
  -p 3000:3000 \
  dstackai/dstack
```

The output of the container is going to be the following:

```bash
To access the application, open this URL in the browser: xxxx://xxxxxxxxxxxx:xxxx/api/users/verify?user=xxxxx&code=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

What's next?
------------
- Check out our documentation: https://docs.dstack.ai
- Ask questions and share feedback: https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ
- Star us on GitHub: https://github.com/dstackai/dstack
```

The link from the output can be used to authenticate without a password. In case you'd like to configure the name and 
password of the admin user, use the `DSTACK_USER` and `DSTACK_PASSWORD` environment variables.

Here's the list of all the environment variables supported by the image:

| Name                         | Required         | Description                                                                                                                                      |
|------------------------------|------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| `AWS_ACCESS_KEY_ID`          | :material-check: | The AWS access key that grants the read/write access to S3<br/> (to store artifacts) and CloudWatch (to store logs).                             |
| `AWS_SECRET_ACCESS_KEY`      | :material-check: | The AWS secret key that grants the read/write access to S3<br/> (to store artifacts) and CloudWatch (to store logs).                             |
| `AWS_DEFAULT_REGION`         | :material-check: | The AWS region to use to store artifacts and logs.                                                                                               |
| `DSTACK_ARTIFACTS_S3_BUCKET` | :material-check: | The name of the AWS S3 bucket to use to store artifacts.                                                                                         |
| `DSTACK_HOSTNAME`            |                  | The hostname at which the dstack server is going to be accessible<br/> by runners and the CLI. The default value is `127.0.0.1`.                 |
| `DSTACK_SSL_ENABLED`         |                  | `true` if the dstack server is going to be accessible by runners<br/> and the CLI via HTTPS, and `false` otherwise. The default value is `false` |
| `DSTACK_PORT`                |                  | The port at which the dstack server is going to be accessible by<br/> runners and the CLI. The default value is `3000`.                          |
| `DSTACK_INTERNAL_PORT`       |                  | The internal port at which the dstack server is running on the machine.<br/> Can be omitted if it's the same as  `DSTACK_PORT`                   |
| `DSTACK_SMTP_HOST`           |                  | The hostname of the SMTP server to send registration confirmation emails.                                                                        |
| `DSTACK_SMTP_USER`           |                  | The user for authentication with the SMTP server when sending <br/>registration confirmation emails.                                             |
| `DSTACK_SMTP_PORT`           |                  | The port of the SMTP server to send registration confirmation emails.                                                                            |
| `DSTACK_SMTP_START_TLS`      |                  | `true` if the SMTP server requires TLS, and `false` otherwise.                                                                                   |
| `DSTACK_USER`                |                  | The name of the admin user. The default value is `dstack`.                                                                                       |
| `DSTACK_PASSWORD`            |                  | The password of the admin user. By default, it's generated automatically.                                                                        |

## Server address

### Server

Use `DSTACK_HOSTNAME`, `DSTACK_SSL_ENABLED`, and `DSTACK_PORT` to configure the address at which the `Server` will be
accessible by runners or the CLI.

For example, if you'd like the dstack `Server` to be accessible at `https://your-dstack-hostname:3000`,
use the following values:

| Name                 | Value                  |
|----------------------|------------------------|
| `DSTACK_HOSTNAME`    | `your-dstack-hostname` |
| `DSTACK_SSL_ENABLED` | `true`                 |
| `DSTACK_PORT`        | `3000`                 |

### Runners and CLI

!!! tip ""
    If you're using `On-demand` `Runners`, the dstack `Server` will configure them automatically.

If you're using `Self-hosted` `Runners`, you'll have to specify them the correct URL of the dstack `Server API Endpoint`:

```bash
dstack-runner config --token <token> --server <server API endpoint>
```

The same when configuring the CLI:

```bash
dstack config --token <token> --server <server API endpoint>
```

When specifying `server API endpoint`, make sure to add `/api` to the end of the address at which the dstack `Server` is running.
It's the address of the dstack `Server API Endpoint` address.
For example, if the `Server` is available at `https://your-dstack-hostname:3000`, the `--server` value 
must be `https://your-dstack-hostname:3000/api`.