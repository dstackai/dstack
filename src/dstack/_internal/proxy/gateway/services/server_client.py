import datetime
import logging
import random
from dataclasses import dataclass, field
from itertools import chain
from pathlib import Path
from typing import Container, Dict, Generator, List

import httpcore
import httpx

logger = logging.getLogger(__name__)
BASE_URL = "http://dstack/"  # any hostname will work


@dataclass
class CachedClientInfo:
    """HTTP client and connection-failure history for one server, owned by HTTPMultiClient."""

    client: httpx.AsyncClient
    socket: Path
    connect_errors: List[datetime.datetime] = field(default_factory=lambda: [])

    def seems_disconnected(self) -> bool:
        # Only ConnectError is recorded; a returned HTTP response clears this history.
        if len(self.connect_errors) < 2:
            return False
        return self.connect_errors[-1] - self.connect_errors[0] >= datetime.timedelta(minutes=2)


class HTTPMultiClient(httpx.AsyncClient):
    """Gateway HTTP client for uncached project-access checks against dstack-server.

    GatewayProxyAuthProvider uses this client and owns authorization decisions and
    their cache. Return the server's HTTP response, including error statuses. Raise
    httpx.RequestError when no connected server can complete the request.
    """

    def __init__(self, sockets_dir: Path):
        super().__init__(base_url=BASE_URL)
        self._sockets_dir = sockets_dir.expanduser()
        self._clients_cache: Dict[str, CachedClientInfo] = {}

    async def send(self, request: httpx.Request, *args, **kwargs) -> httpx.Response:
        errors: List[httpx.RequestError] = []
        clients_count = 0

        # Try another replica after request errors; HTTP error responses are returned.
        for clients_count, client in enumerate(self._iter_clients_rand(), start=1):
            try:
                resp = await client.client.send(request, *args, **kwargs)
                client.connect_errors = []
                return resp
            except httpx.ConnectError:
                client.connect_errors.append(datetime.datetime.now())
                if client.seems_disconnected():
                    logging.debug(
                        "Removing socket %s after several failed connection attempts",
                        client.socket,
                    )
                    client.socket.unlink()
            except httpx.RequestError as e:
                errors.append(e)
                logger.warning("Request failed with socket %s: %r", client.socket, e)

        msg = f"Cannot request {request.url.path}: "
        if not clients_count:
            msg += f"no sockets found in {self._sockets_dir}"
        elif not errors:
            msg += f"all {clients_count} socket(s) in {self._sockets_dir} are disconnected"
        else:
            msg += f"{len(errors)} socket(s) failed. Last error: {errors[-1]!r}"
        raise httpx.RequestError(msg, request=request)

    def _iter_clients_rand(self) -> Generator[CachedClientInfo, None, None]:
        sockets = list(self._sockets_dir.glob("*.sock"))
        self._evict_clients(stems_to_keep={s.stem for s in sockets})
        # Each socket forwards to a server replica; shuffle to distribute auth checks.
        random.shuffle(sockets)

        for socket in sockets:
            if socket.stem in self._clients_cache:
                cached_client = self._clients_cache[socket.stem]
            else:
                cached_client = self._clients_cache[socket.stem] = self._make_client(socket)
            yield cached_client

    @staticmethod
    def _make_client(socket: Path) -> CachedClientInfo:
        client = httpx.AsyncClient(
            transport=_ServerTransport(uds=str(socket.absolute())),
            base_url=BASE_URL,
        )
        return CachedClientInfo(
            client=client,
            socket=socket,
        )

    def _evict_clients(self, stems_to_keep: Container[str]) -> None:
        self._clients_cache = {
            stem: client for stem, client in self._clients_cache.items() if stem in stems_to_keep
        }


class _ServerTransport(httpx.AsyncHTTPTransport):
    """HTTPMultiClient's transport for one dstack-server Unix socket.

    Preserve HTTPX's connection limits and use the request's HTTPX timeouts.
    _ServerConnectionPool provides recovery after overload.
    """

    def __init__(self, uds: str):
        super().__init__(uds=uds)
        # Preserve HTTPX's existing default limits.
        self._pool = _ServerConnectionPool(
            uds=uds,
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=5.0,
        )


class _ServerConnectionPool(httpcore.AsyncConnectionPool):
    """Authorization connection pool used by _ServerTransport, with overload recovery.

    Preserve HTTPcore's connection limits, reuse, ordering and timeout behavior.
    Failed or cancelled requests must not permanently consume capacity or prevent
    later requests from proceeding once connections are available.
    See https://github.com/dstackai/dstack/issues/4338.
    """

    async def handle_async_request(self, request: httpcore.Request) -> httpcore.Response:
        try:
            return await super().handle_async_request(request)
        except BaseException:
            # HTTPcore removes the failed/cancelled request, but can leave its newly
            # assigned connection behind before it starts. That slot is never reused.
            # Remove this orphan cleanup once https://github.com/encode/httpcore/pull/1099 ships.
            with self._optional_thread_lock:
                owners = {id(request.connection) for request in self._requests}
                orphaned = [
                    connection
                    for connection in self._connections
                    if id(connection) not in owners
                    and not connection.is_closed()
                    and not connection.is_available()
                    and not connection.is_idle()
                ]
                if not orphaned:
                    raise
                for connection in orphaned:
                    self._connections.remove(connection)
                # Wake queued requests now that slots are free. Response streams still
                # retain their owners, and HTTPcore shields connection closing below.
                closing = orphaned + self._assign_requests_to_connections()
            await self._close_connections(closing)
            raise

    def _assign_requests_to_connections(self) -> List[httpcore.AsyncConnectionInterface]:
        # Adapted from HTTPcore; see resources/licenses/httpcore.txt.
        if (
            len(self._requests) > len(self._connections)
            and len(self._connections) >= self._max_connections
            and all(
                not connection.is_closed()
                and not connection.has_expired()
                and not connection.is_idle()
                and not connection.is_available()
                for connection in self._connections
            )
        ):
            # A full, busy pool cannot assign or close anything. Scanning every queued
            # request here makes a backlog of timeouts quadratic to drain.
            return []
        closing = []
        for connection in list(self._connections):
            if connection.is_closed():
                self._connections.remove(connection)
            elif connection.has_expired():
                self._connections.remove(connection)
                closing.append(connection)
            elif connection.is_idle() and len(self._connections) > self._max_keepalive_connections:
                # Preserve HTTPcore's existing total-connection keepalive check.
                self._connections.remove(connection)
                closing.append(connection)

        if not self._requests:
            return closing
        if len(self._requests) == 1:
            request = self._requests[0]
            if not request.is_queued():
                return closing
            # Reuse a connection without building lists for a single request.
            origin = request.request.url.origin
            for connection in self._connections:
                if connection.can_handle_request(origin) and connection.is_available():
                    request.assign_to_connection(connection)
                    return closing

        # Skip assignment scans when no request is waiting for a connection.
        queued_requests = (request for request in self._requests if request.is_queued())
        first_request = next(queued_requests, None)
        if first_request is None:
            return closing

        # No connection state changes while this synchronous pass runs. Inspect
        # availability once, rather than scanning every connection for every waiter.
        available = [connection for connection in self._connections if connection.is_available()]
        idle = [connection for connection in self._connections if connection.is_idle()]

        def add_connection(origin: httpcore.Origin) -> httpcore.AsyncConnectionInterface:
            connection = self.create_connection(origin)
            self._connections.append(connection)
            if connection.is_available():
                available.append(connection)
            if connection.is_idle():
                idle.append(connection)
            return connection

        for request in chain((first_request,), queued_requests):
            if len(self._connections) >= self._max_connections and not available and not idle:
                break
            origin = request.request.url.origin
            connection = next(
                (connection for connection in available if connection.can_handle_request(origin)),
                None,
            )
            if connection is not None:
                request.assign_to_connection(connection)
            elif len(self._connections) < self._max_connections:
                request.assign_to_connection(add_connection(origin))
            elif idle:
                connection = idle.pop(0)
                self._connections.remove(connection)
                if connection in available:
                    available.remove(connection)
                closing.append(connection)
                request.assign_to_connection(add_connection(origin))
        return closing
