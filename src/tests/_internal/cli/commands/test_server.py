import os
from unittest.mock import patch

from dstack._internal.cli.commands import server
from tests._internal.cli.common import run_dstack_cli


class TestServerCommand:
    def test_runs_uvicorn_on_asyncio_loop(self):
        with patch.dict(os.environ), patch.object(server.uvicorn, "run") as uvicorn_run:
            assert run_dstack_cli(["server"]) == 0
        assert uvicorn_run.call_args.kwargs["loop"] == "asyncio"
