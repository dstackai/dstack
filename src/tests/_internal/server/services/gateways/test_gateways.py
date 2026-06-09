import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.proxy.gateway.const import SERVICE_SCALING_WINDOWS
from dstack._internal.proxy.gateway.schemas.stats import Stat
from dstack._internal.server.services.gateways import (
    _merge_per_window_stats,
    get_gateway_compute_models,
)
from dstack._internal.server.testing.common import (
    create_backend,
    create_gateway,
    create_gateway_compute,
    create_project,
)


class TestMergePerWindowStats:
    def test_empty_returns_zero_stats(self):
        result = _merge_per_window_stats([])
        for window in SERVICE_SCALING_WINDOWS:
            assert result[window].requests == 0
            assert result[window].request_time == 0.0

    def test_single_replica_returns_same_values(self):
        stats = {w: Stat(requests=10, request_time=0.5) for w in SERVICE_SCALING_WINDOWS}
        result = _merge_per_window_stats([stats])
        for window in SERVICE_SCALING_WINDOWS:
            assert result[window].requests == 10
            assert result[window].request_time == pytest.approx(0.5)

    def test_multiple_replicas_sums_requests_and_averages_time(self):
        stats_a = {w: Stat(requests=10, request_time=1.0) for w in SERVICE_SCALING_WINDOWS}
        stats_b = {w: Stat(requests=30, request_time=3.0) for w in SERVICE_SCALING_WINDOWS}
        result = _merge_per_window_stats([stats_a, stats_b])
        for window in SERVICE_SCALING_WINDOWS:
            assert result[window].requests == 40
            assert result[window].request_time == pytest.approx(2.5)  # (10*1 + 30*3) / 40

    def test_zero_requests_across_all_replicas_returns_zero_time(self):
        stats_a = {w: Stat(requests=0, request_time=0.0) for w in SERVICE_SCALING_WINDOWS}
        stats_b = {w: Stat(requests=0, request_time=0.0) for w in SERVICE_SCALING_WINDOWS}
        result = _merge_per_window_stats([stats_a, stats_b])
        for window in SERVICE_SCALING_WINDOWS:
            assert result[window].requests == 0
            assert result[window].request_time == 0.0


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestGetGatewayComputeModels:
    async def test_new_style_returns_gateway_computes(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session, project_id=project.id, backend_id=backend.id
        )
        compute = await create_gateway_compute(
            session=session, gateway_id=gateway.id, backend_id=backend.id
        )
        await session.refresh(gateway, ["gateway_computes", "gateway_compute"])
        result = get_gateway_compute_models(gateway)
        assert len(result) == 1
        assert result[0].id == compute.id

    async def test_old_style_returns_single_compute(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        compute = await create_gateway_compute(session=session, backend_id=backend.id)
        gateway = await create_gateway(
            session=session, project_id=project.id, backend_id=backend.id
        )
        gateway.gateway_compute_id = compute.id
        await session.commit()
        await session.refresh(gateway, ["gateway_computes", "gateway_compute"])
        result = get_gateway_compute_models(gateway)
        assert len(result) == 1
        assert result[0].id == compute.id

    async def test_no_computes_returns_empty(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session, project_id=project.id, backend_id=backend.id
        )
        await session.refresh(gateway, ["gateway_computes", "gateway_compute"])
        result = get_gateway_compute_models(gateway)
        assert result == []
