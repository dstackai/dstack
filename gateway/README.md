# dstack gateway

## Purpose

* Make dstack services available to the outside world
* Manage SSL certificates
* Manage nginx configs
* Establish SSH tunnels from gateway to dstack runner
* Proxy OpenAI API requests to different formats (e.g. TGI)

## Development

1. Run `dstack server` with `DSTACK_SKIP_GATEWAY_UPDATE=1` environment variable. This will prevent dstack from updating the gateway to standard version on each server restart.

1. Provision a gateway through dstack:

   ```shell
   dstack gateway create --backend aws --region us-east-1 --domain my.wildcard.domain.com
   ```

1. Save the gateway key to a file. You can find the key in sqlite, e.g.:

   ```shell
   sqlite3 ~/.dstack/server/data/sqlite.db "SELECT ip_address, ssh_private_key FROM gateway_computes"
   ```

1. Build gateway locally and deploy it:

   ```shell
   HOST=ubuntu@x.my.wildcard.domain.com
   ID_RSA=/path/to/the/gateway/key
   WHEEL=dstack_gateway-0.0.0-py3-none-any.whl
   
   python -m build .
   scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i "${ID_RSA}" "./dist/${WHEEL}" "${HOST}":/tmp/
   ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i "${ID_RSA}" "${HOST}" "/bin/sh /home/ubuntu/dstack/update.sh /tmp/${WHEEL} dev"
   ```

1. Open SSH tunnel to the gateway:

   ```shell
   ssh -L 9001:localhost:8000 -i "${ID_RSA}" "${HOST}"
   ```

1. Visit the gateway docs page at http://localhost:9001/docs

1. To follow logs, use this command in SSH:

   ```shell
   journalctl -u dstack.gateway.service -f
   ```
