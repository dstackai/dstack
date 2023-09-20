import asyncio
import weakref
from typing import BinaryIO, Dict, Optional

import aiohttp

from dstack._internal.core.models.repos.remote import RemoteRepoCreds
from dstack._internal.core.models.runs import JobSpec, RunSpec
from dstack._internal.server.schemas.runner import PullResponse, SubmitBody


class AsyncRunnerClient:
    def __init__(
        self,
        port: int,
        hostname: str = "localhost",
        session: Optional[aiohttp.ClientSession] = None,
    ):
        self.secure = False
        self.hostname = hostname
        self.port = port
        if session is None:
            self.session = aiohttp.ClientSession()
            self._session_finalizer = weakref.finalize(self, self._close_session)
        else:
            self.session = session

    async def healthcheck(self) -> bool:
        try:
            async with self.session.get(self._url("/api/healthcheck")) as resp:
                return resp.status == 200
        except aiohttp.ClientError:
            return False

    async def submit_job(
        self,
        run_spec: RunSpec,
        job_spec: JobSpec,
        secrets: Dict[str, str],
        repo_credentials: Optional[RemoteRepoCreds],
    ):
        body = SubmitBody(
            run_spec=run_spec,
            job_spec=job_spec,
            secrets=secrets,
            repo_credentials=repo_credentials,
        )
        async with self.session.post(self._url("/api/submit"), json=body.dict()) as resp:
            resp.raise_for_status()

    async def upload_code(self, file: BinaryIO):
        async with self.session.post(self._url("/api/upload_code"), data=file) as resp:
            resp.raise_for_status()

    async def run_job(self):
        async with self.session.post(self._url("/api/run")) as resp:
            resp.raise_for_status()

    async def pull(self, timestamp: int) -> PullResponse:
        async with self.session.get(
            self._url("/api/pull"), params={"timestamp": timestamp}
        ) as resp:
            resp.raise_for_status()
            return PullResponse.parse_obj(await resp.json())

    async def stop(self):
        async with self.session.post(self._url("/api/stop")) as resp:
            resp.raise_for_status()

    def _url(self, path: str) -> str:
        return f"{'https' if self.secure else 'http'}://{self.hostname}:{self.port}/{path.lstrip('/')}"

    def _close_session(self):
        asyncio.run(self.session.close())
