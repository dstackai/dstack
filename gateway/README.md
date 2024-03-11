# dstack gateway

## Purpose

* Make dstack services available to the outside world
* Manage SSL certificates
* Manage nginx configs
* Establish SSH tunnels from gateway to dstack runner
* Proxy OpenAI API requests to different formats (e.g. TGI)

## Development

1. Provision a gateway through dstack:
   ```shell
   dstack gateway create --backend aws --region us-east-1 --domain my.wildcard.domain.com
   ```
2. Extract the project key from the sqlite to the file
3. Build gateway locally and deploy it:
   ```shell
   HOST=ubuntu@x.my.wildcard.domain.com
   ID_RSA=/path/to/the/project/key
   WHEEL=dstack_gateway-0.0.0-py3-none-any.whl
   
   python -m build .
   scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i "${ID_RSA}" "./dist/${WHEEL}" "${HOST}":/tmp/
   ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i "${ID_RSA}" "${HOST}" "/bin/sh /home/ubuntu/dstack/update.sh /tmp/${WHEEL} dev"
   ```
4. Open SSH tunnel to the gateway:
   ```shell
   ssh -L 9001:localhost:8000 -i "${ID_RSA}" "${HOST}"
   ```
5. Visit the gateway docs page at http://localhost:9001/docs

To follow logs, use the command:
```shell
journalctl -u dstack.gateway.service -f
```
