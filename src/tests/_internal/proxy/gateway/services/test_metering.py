import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import time_machine

from dstack._internal.proxy.gateway.services.metering import GatewayProxyMeter
from dstack._internal.proxy.lib.auth import ProxyCaller
from dstack._internal.proxy.lib.testing.common import make_service

CALLER = ProxyCaller(project_id=uuid.uuid4(), user_id=uuid.uuid4())
SERVICE = make_service("test-proj", "test-run")


def add(meter: GatewayProxyMeter, input_tokens: int = 1) -> None:
    meter.add(
        CALLER, SERVICE, None, input_tokens=input_tokens, cached_input_tokens=0, output_tokens=0
    )


@pytest.mark.asyncio
class TestGatewayProxyMeter:
    async def test_writes_one_record_per_hour_caller_and_service(self, tmp_path: Path):
        meter = GatewayProxyMeter(tmp_path)
        other_caller = ProxyCaller(project_id=CALLER.project_id, user_id=uuid.uuid4())
        with time_machine.travel(datetime(2026, 11, 20, 10, 59, tzinfo=timezone.utc), tick=False):
            meter.add(
                CALLER, SERVICE, None, input_tokens=800, cached_input_tokens=700, output_tokens=5
            )
            meter.add(
                CALLER, SERVICE, None, input_tokens=0, cached_input_tokens=0, output_tokens=10
            )
            meter.add(
                other_caller, SERVICE, None, input_tokens=3, cached_input_tokens=0, output_tokens=1
            )
        with time_machine.travel(
            datetime(2026, 11, 20, 11, 0, 5, tzinfo=timezone.utc), tick=False
        ):
            # The rest of a request that runs past the turn of the hour
            meter.add(
                CALLER, SERVICE, None, input_tokens=0, cached_input_tokens=0, output_tokens=7
            )
            await meter.flush()

        assert json.loads((tmp_path / "1.json").read_text()) == {
            "batch_no": 1,
            "created_at": "2026-11-20T11:00:05Z",
            "records": [
                {
                    "hour": "2026-11-20T10:00:00Z",
                    "project_id": str(CALLER.project_id),
                    "user_id": str(CALLER.user_id),
                    "run_id": str(uuid.UUID(SERVICE.id)),
                    "export_id": None,
                    "input_tokens": 800,
                    "cached_input_tokens": 700,
                    "output_tokens": 15,
                },
                {
                    "hour": "2026-11-20T10:00:00Z",
                    "project_id": str(CALLER.project_id),
                    "user_id": str(other_caller.user_id),
                    "run_id": str(uuid.UUID(SERVICE.id)),
                    "export_id": None,
                    "input_tokens": 3,
                    "cached_input_tokens": 0,
                    "output_tokens": 1,
                },
                {
                    "hour": "2026-11-20T11:00:00Z",
                    "project_id": str(CALLER.project_id),
                    "user_id": str(CALLER.user_id),
                    "run_id": str(uuid.UUID(SERVICE.id)),
                    "export_id": None,
                    "input_tokens": 0,
                    "cached_input_tokens": 0,
                    "output_tokens": 7,
                },
            ],
        }

    async def test_writes_requests_through_an_export_to_a_record_with_the_export(
        self, tmp_path: Path
    ):
        meter = GatewayProxyMeter(tmp_path)
        export_id = uuid.uuid4()
        add(meter, input_tokens=1)
        for input_tokens in (2, 3):
            meter.add(
                CALLER,
                SERVICE,
                export_id.hex,
                input_tokens=input_tokens,
                cached_input_tokens=0,
                output_tokens=0,
            )
        await meter.flush()

        records = json.loads((tmp_path / "1.json").read_text())["records"]
        assert [(record["export_id"], record["input_tokens"]) for record in records] == [
            (None, 1),
            (str(export_id), 5),
        ]
        (batch,) = await meter.collect(after=0, limit=1)
        assert [record.export_id for record in batch.records] == [None, export_id]

    async def test_collects_batches_after_the_given_one_and_deletes_the_saved(
        self, tmp_path: Path
    ):
        meter = GatewayProxyMeter(tmp_path)
        for input_tokens in (1, 2, 3, 4):
            add(meter, input_tokens)
            await meter.flush()

        batches = await meter.collect(after=1, limit=2)
        assert [batch.batch_no for batch in batches] == [2, 3]
        assert [batch.records[0].input_tokens for batch in batches] == [2, 3]
        # The batches after the given one stay until the server confirms them.
        assert sorted(path.name for path in tmp_path.glob("*.json")) == [
            "2.json",
            "3.json",
            "4.json",
        ]

        assert [batch.batch_no for batch in await meter.collect(after=3, limit=2)] == [4]
        assert await meter.collect(after=4, limit=2) == []
        assert list(tmp_path.glob("*.json")) == []

    async def test_numbers_new_batches_above_the_ones_the_server_saved(self, tmp_path: Path):
        # The gateway's files were lost, so it starts from 1, while the server has saved 41.
        meter = GatewayProxyMeter(tmp_path)
        add(meter)
        await meter.flush()
        assert await meter.collect(after=41, limit=100) == []
        add(meter)
        await meter.flush()
        assert [batch.batch_no for batch in await meter.collect(after=41, limit=100)] == [42]

    async def test_continues_numbering_after_restart(self, tmp_path: Path):
        meter = GatewayProxyMeter(tmp_path)
        for _ in range(2):
            add(meter)
            await meter.flush()
        # All batches are collected and deleted before the restart.
        assert await meter.collect(after=2, limit=100) == []

        meter = GatewayProxyMeter(tmp_path)
        add(meter)
        await meter.flush()
        assert [batch.batch_no for batch in await meter.collect(after=2, limit=100)] == [3]

        # The number is also taken from the batch files, if they are ahead of the stored one.
        (tmp_path / "last_batch_no").unlink()
        meter = GatewayProxyMeter(tmp_path)
        add(meter)
        await meter.flush()
        assert [batch.batch_no for batch in await meter.collect(after=2, limit=100)] == [3, 4]

    async def test_deletes_batches_older_than_seven_days(self, tmp_path: Path):
        meter = GatewayProxyMeter(tmp_path)
        for _ in range(2):
            add(meter)
            await meter.flush()
        eight_days_ago = datetime.now(tz=timezone.utc).timestamp() - 8 * 24 * 3600
        os.utime(tmp_path / "1.json", (eight_days_ago, eight_days_ago))

        # A restarted gateway deletes old batches on its first flush.
        meter = GatewayProxyMeter(tmp_path)
        await meter.flush()
        assert [path.name for path in tmp_path.glob("*.json")] == ["2.json"]

    async def test_keeps_counts_if_the_batch_cannot_be_written(self, tmp_path: Path):
        meter = GatewayProxyMeter(tmp_path / "metering")
        (tmp_path / "metering").write_text("not a directory")
        add(meter, input_tokens=5)
        with pytest.raises(OSError):
            await meter.flush()
        (tmp_path / "metering").unlink()
        add(meter, input_tokens=2)
        await meter.flush()
        (batch,) = await meter.collect(after=0, limit=100)
        assert batch.records[0].input_tokens == 7
