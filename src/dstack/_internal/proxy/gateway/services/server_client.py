import datetime
import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Container, Dict, Generator, List

import httpx

logger = logging.getLogger(__name__)
BASE_URL = "http://dstack/"  # any hostname will work


@dataclass
class CachedClientInfo:
    client: httpx.AsyncClient
    socket: Path
    connect_errors: List[datetime.datetime] = field(default_factory=lambda: [])

    def seems_disconnected(self) -> bool:
        if len(self.connect_errors) < 2:
            return False
        return self.connect_errors[-1] - self.connect_errors[0] >= datetime.timedelta(minutes=2)


class HTTPMultiClient(httpx.AsyncClient):
    """
    An HTTP client that sends requests to randomly chosen Unix sockets from a specified
    directory. This allows to balance the load between multiple HTTP server replicas.
    Automatically deletes sockets that stop responding.
    Used for requesting random dstack-server replicas from the gateway.
    """

    def __init__(self, sockets_dir: Path):
        super().__init__(base_url=BASE_URL)
        self._sockets_dir = sockets_dir.expanduser()
        self._clients_cache: Dict[str, CachedClientInfo] = {}

    async def send(self, request: httpx.Request, *args, **kwargs) -> httpx.Response:
        errors: List[httpx.RequestError] = []
        clients_count = 0

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
            transport=httpx.AsyncHTTPTransport(uds=str(socket.absolute())),
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
