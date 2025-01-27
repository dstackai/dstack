# Gateway

A `dstack` gateway is a dedicated instance responsible for publishing user applications to the outer internet via the HTTP protocol. One dstack gateway can serve many services, domains, or projects.

## Gateway creation

Gateways are managed by the `dstack` server. A gateway is associated with a project and some backend in the project. Users must attach a wildcard domain to the gateway, i.e., all direct subdomains should resolve to the gateway IP address. Since the IP address is unknown during provisioning, `dstack` doesn't check DNS records.

Provisioning happens as follows:
1. Launch a non-GPU instance (usually the smallest) with all ports exposed.
2. Install Nginx, Certbot, and patch configs.
3. Create blue-green virtual environments.
4. Install the latest `dstack-gateway` from the S3 bucket.
5. Run the systemd service `dstack.gateway.service`.

## Gateway update

The `dstack-gateway` has a "blue-green deployment"-like configuration: there are two virtual environments to be swapped on update. The systemd service uses the newly installed package after a restart.

The update process looks like this:
1. Install the new package to the not-used venv.
2. Update scripts and systemd service config.
3. Swap the active venv name in the file `version`.
4. Restart the systemd service.

The `dstack-gateway` server dumps its internal state to the file `~/dstack/state.json` on termination. It tries to load the state from the same file on start. That allows updating the gateway with published services with minimal downtime.

## Connection between server and gateway

The `dstack` server keeps a bidirectional tunnel with each GatewayCompute for the whole uptime of the server.

- The tunnel from the server to the gateway is used to manage the gateway: register and unregister services and replicas.
- The tunnel from the gateway to the server is used to authenticate requests to the gateway based on dstack's tokens.

Authorization responses are cached for 60 seconds. If the server is not responding, the request is denied.

## Nginx

`dstack-gateway` configures an Nginx reverse proxy. Each service or entrypoint configuration is stored as `/etc/nginx/sites-enabled/{port}-{server_name}.conf`. If the Nginx reload fails, `dstack-gateway` rolls back the changes.

`dstack-gateway` enforces HTTPS (except for local traffic). On each service registration a TLS certificate is issued by Let's Encrypt or other configured CA via Certbot.

If there are no replicas, the service configuration always returns 503; otherwise, the upstream with replicas is used. The upstream handles load balancing for us. `dstack-gateway` uses Unix sockets for SSH tunnels to avoid port conflicts between services.

Service authorization is handled with the `localhost:8000/auth` endpoint if needed. `dstack-gateway` may request services without authorization and HTTPS, for example, from the OpenAI interface.

Entrypoint configurations forward requests back to `dstack-gateway`, to a specific module (e.g., OpenAI). Authorization is handled by those modules.

## Gateway registry

The core component of `dstack-gateway` is the services store. It is responsible for:

- Registering a service — assigning a domain, creating an Nginx config.
- Registering a replica — starting an SSH tunnel, updating Nginx upstream.
- Unregistering a replica — stopping an SSH tunnel, updating Nginx upstream.
- Unregistering a service — releasing a domain, removing an Nginx config.
- Registering an entrypoint — assigning a domain, creating an Nginx config.

To decouple the store from other modules, there is a subscription mechanism. Subscribers will be notified on register service and unregister service.

## OpenAI interface

The OpenAI interface subscribes to `Store` events and emulates the real OpenAI API for chat completion models. It can list running models in the project and redirect requests to the right service.

## Stats Collector

The Stats collector parses nginx `/var/log/nginx/dstack.access.log` to collect basic metrics:

1. Requests per second
2. Average request processing time

By default, it stores 5 minutes with 1-second resolution frames for each domain. It aggregates these frames in windows of the size 30 seconds, 1 minute, and 5 minutes, before sending to the server.

To increase performance, `StatsCollector` keeps position in file and read only new records. It can detect log rotation and reopen the log file.
