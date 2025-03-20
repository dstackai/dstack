from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.metrics import Metric
from dstack._internal.server.services.metrics import get_job_metrics
from dstack._internal.server.testing.common import (
    create_job,
    create_job_metrics_point,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_job_provisioning_data,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("test_db", "image_config_mock")
class TestGetMetrics:
    latest_ts = datetime(2023, 1, 2, 3, 4, 25, tzinfo=timezone.utc)
    ts: tuple[datetime, ...] = (
        latest_ts,  # 0
        latest_ts - timedelta(seconds=10),  # 1
        latest_ts - timedelta(seconds=20),  # 2
        latest_ts - timedelta(seconds=30),  # 3
        latest_ts - timedelta(seconds=40),  # 4
        latest_ts - timedelta(seconds=50),  # 5
    )
    # dt, cpu_usage_sec, memory_usage_bytes, memory_ws_bytes, gpu0_memory_usage_bytes, gpu0_util,
    # gpu1_memory_usage_bytess, gpu1_util
    points: tuple[tuple[datetime, int, int, int, int, int, int, int], ...] = (
        (ts[0], 110, 512, 128, 768, 15, 128, 20),
        (ts[1], 104, 1024, 512, 1024, 10, 256, 10),
        (ts[2], 100, 1024, 512, 1024, 20, 128, 5),
        (ts[3], 90, 512, 512, 2048, 40, 512, 20),
        (ts[4], 90, 1024, 1024, 1024, 0, 128, 0),
        (ts[5], 80, 512, 512, 1024, 10, 256, 0),
    )

    @pytest.mark.parametrize(
        ["params", "ts", "cpu", "mem", "mem_ws", "gpu0_mem", "gpu0_util", "gpu1_mem", "gpu1_util"],
        [
            pytest.param(
                {"limit": 1},
                [ts[0]],
                [60],
                [512],
                [128],
                [768],
                [15],
                [128],
                [20],
                id="limit-1-latest",
            ),
            pytest.param(
                {"limit": 3},
                [ts[0], ts[1], ts[2]],
                [60, 40, 100],
                [512, 1024, 1024],
                [128, 512, 512],
                [768, 1024, 1024],
                [15, 10, 20],
                [128, 256, 128],
                [20, 10, 5],
                id="limit-3-latest",
            ),
            pytest.param(
                {},
                [ts[0], ts[1], ts[2], ts[3], ts[4]],
                [60, 40, 100, 0, 100],
                [512, 1024, 1024, 512, 1024],
                [128, 512, 512, 512, 1024],
                [768, 1024, 1024, 2048, 1024],
                [15, 10, 20, 40, 0],
                [128, 256, 128, 512, 128],
                [20, 10, 5, 20, 0],
                id="all",
            ),
            pytest.param(
                {"after": ts[3]},
                [ts[0], ts[1], ts[2]],
                [60, 40, 100],
                [512, 1024, 1024],
                [128, 512, 512],
                [768, 1024, 1024],
                [15, 10, 20],
                [128, 256, 128],
                [20, 10, 5],
                id="all-after",
            ),
            pytest.param(
                {"before": ts[2]},
                [ts[3], ts[4]],
                [0, 100],
                [512, 1024],
                [512, 1024],
                [2048, 1024],
                [40, 0],
                [512, 128],
                [20, 0],
                id="all-before",
            ),
        ],
    )
    async def test_get_metrics(
        self,
        session: AsyncSession,
        params: dict,
        ts: list[datetime],
        cpu: list[int],
        mem: list[int],
        mem_ws: list[int],
        gpu0_mem: list[int],
        gpu0_util: list[int],
        gpu1_mem: list[int],
        gpu1_util: list[int],
    ):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
        )
        jpd = get_job_provisioning_data(
            cpu_count=64, memory_gib=128, gpu_count=2, gpu_memory_gib=32
        )
        job = await create_job(
            session=session,
            run=run,
            job_provisioning_data=jpd,
        )
        for dt, _cpu, _mem, _mem_ws, _gpu0_mem, _gpu0_util, _gpu1_mem, _gpu1_util in self.points:
            await create_job_metrics_point(
                session=session,
                job_model=job,
                timestamp=dt,
                cpu_usage_micro=_cpu * 1_000_000,
                memory_usage_bytes=_mem,
                memory_working_set_bytes=_mem_ws,
                gpus_memory_usage_bytes=[_gpu0_mem, _gpu1_mem],
                gpus_util_percent=[_gpu0_util, _gpu1_util],
            )

        metrics = await get_job_metrics(session, job, **params)

        assert metrics.metrics == [
            Metric(name="cpu_usage_percent", timestamps=ts, values=cpu),
            Metric(name="memory_usage_bytes", timestamps=ts, values=mem),
            Metric(name="memory_working_set_bytes", timestamps=ts, values=mem_ws),
            Metric(name="cpus_detected_num", timestamps=ts, values=[64] * len(ts)),
            Metric(name="memory_total_bytes", timestamps=ts, values=[137438953472] * len(ts)),
            Metric(name="gpus_detected_num", timestamps=ts, values=[2] * len(ts)),
            Metric(name="gpu_memory_total_bytes", timestamps=ts, values=[34359738368] * len(ts)),
            Metric(name="gpu_memory_usage_bytes_gpu0", timestamps=ts, values=gpu0_mem),
            Metric(name="gpu_memory_usage_bytes_gpu1", timestamps=ts, values=gpu1_mem),
            Metric(name="gpu_util_percent_gpu0", timestamps=ts, values=gpu0_util),
            Metric(name="gpu_util_percent_gpu1", timestamps=ts, values=gpu1_util),
        ]
