from typing import Dict, List, Optional
from unittest.mock import Mock, patch

import gpuhunt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    Gpu,
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_project,
    create_repo,
    create_user,
    get_auth_headers,
    get_run_spec,
)

pytestmark = pytest.mark.usefixtures("image_config_mock")


# GPU Test Fixtures and Helpers


async def gpu_test_setup(session: AsyncSession):
    """Common setup for GPU tests: user, project, repo, run_spec."""
    user = await create_user(session=session, global_role=GlobalRole.USER)
    project = await create_project(session=session, owner=user)
    await add_project_member(
        session=session, project=project, user=user, project_role=ProjectRole.USER
    )
    repo = await create_repo(session=session, project_id=project.id)
    run_spec = get_run_spec(run_name="test-run", repo_id=repo.name)
    return user, project, repo, run_spec


def create_gpu_offer(
    backend: BackendType,
    gpu_name: str,
    gpu_memory_mib: int,
    price: float,
    spot: bool = False,
    region: str = "us-west-2",
    availability: InstanceAvailability = InstanceAvailability.AVAILABLE,
    gpu_count: int = 1,
    instance_name: Optional[str] = None,
    vendor: gpuhunt.AcceleratorVendor = gpuhunt.AcceleratorVendor.NVIDIA,
) -> InstanceOfferWithAvailability:
    """Helper to create GPU offers with sensible defaults."""
    if instance_name is None:
        instance_name = f"{gpu_name.lower()}-instance"

    gpus = [Gpu(name=gpu_name, memory_mib=gpu_memory_mib, vendor=vendor) for _ in range(gpu_count)]
    cpus = max(4, gpu_count * 4)
    memory_mib = max(16384, gpu_count * 16384)

    return InstanceOfferWithAvailability(
        backend=backend,
        instance=InstanceType(
            name=instance_name,
            resources=Resources(cpus=cpus, memory_mib=memory_mib, spot=spot, gpus=gpus),
        ),
        region=region,
        price=price,
        availability=availability,
    )


def create_mock_backends_with_offers(
    offers_by_backend: Dict[BackendType, List[InstanceOfferWithAvailability]],
) -> List[Mock]:
    """Helper to create mocked backends with specific offers."""
    mocked_backends = []

    for backend_type, offers in offers_by_backend.items():
        backend_mock = Mock()
        backend_mock.TYPE = backend_type
        backend_mock.compute.return_value.get_offers_cached.return_value = offers
        mocked_backends.append(backend_mock)

    return mocked_backends


async def call_gpus_api(
    client: AsyncClient,
    project_name: str,
    user_token: str,
    run_spec: RunSpec,
    group_by: Optional[List[str]] = None,
):
    """Helper to call the GPUs API with standard parameters."""
    json_data = {"run_spec": run_spec.dict()}
    if group_by is not None:
        json_data["group_by"] = group_by

    return await client.post(
        f"/api/project/{project_name}/gpus/list",
        headers=get_auth_headers(user_token),
        json=json_data,
    )


class TestListGpus:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_project_member(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        run_spec = get_run_spec(run_name="test-run", repo_id="test-repo")
        response = await call_gpus_api(client, project.name, user.token, run_spec)
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_gpus_without_group_by(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user, project, repo, run_spec = await gpu_test_setup(session)

        offer_aws = create_gpu_offer(BackendType.AWS, "T4", 16384, 0.50, spot=False)
        offer_runpod = create_gpu_offer(
            BackendType.RUNPOD, "RTX4090", 24576, 0.35, spot=True, region="us-east-1"
        )
        offers_by_backend = {BackendType.AWS: [offer_aws], BackendType.RUNPOD: [offer_runpod]}
        mocked_backends = create_mock_backends_with_offers(offers_by_backend)

        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = mocked_backends
            response = await call_gpus_api(client, project.name, user.token, run_spec)

        assert response.status_code == 200
        response_data = response.json()
        assert "gpus" in response_data
        assert isinstance(response_data["gpus"], list)
        assert len(response_data["gpus"]) >= 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_empty_gpus_when_no_offers(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(run_name="test-run", repo_id=repo.name)

        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock_aws = Mock()
            backend_mock_aws.TYPE = BackendType.AWS
            backend_mock_aws.compute.return_value.get_offers_cached.return_value = []
            m.return_value = [backend_mock_aws]

            response = await client.post(
                f"/api/project/{project.name}/gpus/list",
                headers=get_auth_headers(user.token),
                json={"run_spec": run_spec.dict()},
            )

        assert response.status_code == 200
        response_data = response.json()
        assert "gpus" in response_data
        assert isinstance(response_data["gpus"], list)
        assert len(response_data["gpus"]) == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_invalid_group_by_rejected(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        """Test that invalid group_by values are properly rejected."""
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(run_name="test-run", repo_id=repo.name)

        response = await client.post(
            f"/api/project/{project.name}/gpus/list",
            headers=get_auth_headers(user.token),
            json={"run_spec": run_spec.dict(), "group_by": ["invalid_field"]},
        )
        assert response.status_code == 422
        assert "validation error" in response.text.lower() or "invalid" in response.text.lower()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_region_without_backend_rejected(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user, project, repo, run_spec = await gpu_test_setup(session)

        response = await call_gpus_api(
            client, project.name, user.token, run_spec, group_by=["region"]
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_exact_aggregation_values(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        """Test exact aggregation values with precise validation (no >= or <=)."""
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(run_name="test-run", repo_id=repo.name)

        offer_t4_spot = InstanceOfferWithAvailability(
            backend=BackendType.AWS,
            instance=InstanceType(
                name="g4dn.xlarge",
                resources=Resources(
                    cpus=4,
                    memory_mib=16384,
                    spot=True,
                    gpus=[
                        Gpu(name="T4", memory_mib=16384, vendor=gpuhunt.AcceleratorVendor.NVIDIA)
                    ],
                ),
            ),
            region="us-west-2",
            price=0.30,
            availability=InstanceAvailability.AVAILABLE,
        )
        offer_t4_ondemand = InstanceOfferWithAvailability(
            backend=BackendType.AWS,
            instance=InstanceType(
                name="g4dn.2xlarge",
                resources=Resources(
                    cpus=8,
                    memory_mib=32768,
                    spot=False,
                    gpus=[
                        Gpu(name="T4", memory_mib=16384, vendor=gpuhunt.AcceleratorVendor.NVIDIA)
                    ],
                ),
            ),
            region="us-west-2",
            price=0.60,
            availability=InstanceAvailability.AVAILABLE,
        )
        offer_t4_quota = InstanceOfferWithAvailability(
            backend=BackendType.AWS,
            instance=InstanceType(
                name="g4dn.4xlarge",
                resources=Resources(
                    cpus=16,
                    memory_mib=65536,
                    spot=True,
                    gpus=[
                        Gpu(name="T4", memory_mib=16384, vendor=gpuhunt.AcceleratorVendor.NVIDIA)
                    ],
                ),
            ),
            region="us-east-1",
            price=0.45,
            availability=InstanceAvailability.NO_QUOTA,
        )
        offer_t4_multi = InstanceOfferWithAvailability(
            backend=BackendType.AWS,
            instance=InstanceType(
                name="g4dn.12xlarge",
                resources=Resources(
                    cpus=48,
                    memory_mib=196608,
                    spot=False,
                    gpus=[
                        Gpu(name="T4", memory_mib=16384, vendor=gpuhunt.AcceleratorVendor.NVIDIA),
                        Gpu(name="T4", memory_mib=16384, vendor=gpuhunt.AcceleratorVendor.NVIDIA),
                        Gpu(name="T4", memory_mib=16384, vendor=gpuhunt.AcceleratorVendor.NVIDIA),
                        Gpu(name="T4", memory_mib=16384, vendor=gpuhunt.AcceleratorVendor.NVIDIA),
                    ],
                ),
            ),
            region="us-west-2",
            price=2.40,
            availability=InstanceAvailability.AVAILABLE,
        )

        offer_runpod_rtx_east = create_gpu_offer(
            BackendType.RUNPOD, "RTX4090", 24576, 0.75, spot=True, region="us-east-1"
        )
        offer_runpod_rtx_eu = create_gpu_offer(
            BackendType.RUNPOD, "RTX4090", 24576, 0.65, spot=False, region="eu-west-1"
        )
        offer_runpod_t4_east = create_gpu_offer(
            BackendType.RUNPOD, "T4", 16384, 0.25, spot=True, region="us-east-1"
        )

        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock_aws = Mock()
            backend_mock_aws.TYPE = BackendType.AWS
            backend_mock_aws.compute.return_value.get_offers_cached.return_value = [
                offer_t4_spot,
                offer_t4_ondemand,
                offer_t4_quota,
                offer_t4_multi,
            ]

            backend_mock_runpod = Mock()
            backend_mock_runpod.TYPE = BackendType.RUNPOD
            backend_mock_runpod.compute.return_value.get_offers_cached.return_value = [
                offer_runpod_rtx_east,
                offer_runpod_rtx_eu,
                offer_runpod_t4_east,
            ]

            m.return_value = [backend_mock_aws, backend_mock_runpod]

            response = await client.post(
                f"/api/project/{project.name}/gpus/list",
                headers=get_auth_headers(user.token),
                json={"run_spec": run_spec.dict()},
            )
            assert response.status_code == 200
            data = response.json()

            assert len(data["gpus"]) == 2

            t4_gpu = next((gpu for gpu in data["gpus"] if gpu["name"] == "T4"), None)
            rtx_gpu = next((gpu for gpu in data["gpus"] if gpu["name"] == "RTX4090"), None)

            assert t4_gpu is not None
            assert rtx_gpu is not None

            assert t4_gpu["price"]["min"] == 0.25
            assert t4_gpu["price"]["max"] == 0.60
            assert set(t4_gpu["backends"]) == {"aws", "runpod"}

            assert rtx_gpu["price"]["min"] == 0.65
            assert rtx_gpu["price"]["max"] == 0.75
            assert set(rtx_gpu["backends"]) == {"runpod"}

            response_count_grouped = await client.post(
                f"/api/project/{project.name}/gpus/list",
                headers=get_auth_headers(user.token),
                json={"run_spec": run_spec.dict(), "group_by": ["count"]},
            )
            assert response_count_grouped.status_code == 200
            count_grouped_data = response_count_grouped.json()

            assert len(count_grouped_data["gpus"]) == 3

            t4_single_group = None
            t4_multi_group = None
            rtx_single_group = None

            for gpu in count_grouped_data["gpus"]:
                if gpu["name"] == "T4" and gpu["count"]["min"] == 1 and gpu["count"]["max"] == 1:
                    t4_single_group = gpu
                elif gpu["name"] == "T4" and gpu["count"]["min"] == 4 and gpu["count"]["max"] == 4:
                    t4_multi_group = gpu
                elif (
                    gpu["name"] == "RTX4090"
                    and gpu["count"]["min"] == 1
                    and gpu["count"]["max"] == 1
                ):
                    rtx_single_group = gpu

            assert t4_single_group is not None
            assert t4_multi_group is not None
            assert rtx_single_group is not None

            assert t4_single_group["price"]["min"] == 0.25
            assert t4_single_group["price"]["max"] == 0.60
            assert t4_multi_group["price"]["min"] == 0.60
            assert t4_multi_group["price"]["max"] == 0.60
            assert rtx_single_group["price"]["min"] == 0.65
            assert rtx_single_group["price"]["max"] == 0.75

            assert set(t4_single_group["backends"]) == {"aws", "runpod"}
            assert set(t4_multi_group["backends"]) == {"aws"}

            response_backend = await client.post(
                f"/api/project/{project.name}/gpus/list",
                headers=get_auth_headers(user.token),
                json={"run_spec": run_spec.dict(), "group_by": ["backend"]},
            )
            assert response_backend.status_code == 200
            backend_data = response_backend.json()

            assert len(backend_data["gpus"]) == 3

            t4_runpod = next(
                (
                    gpu
                    for gpu in backend_data["gpus"]
                    if gpu["name"] == "T4" and gpu.get("backend") == "runpod"
                ),
                None,
            )
            t4_aws = next(
                (
                    gpu
                    for gpu in backend_data["gpus"]
                    if gpu["name"] == "T4" and gpu.get("backend") == "aws"
                ),
                None,
            )
            rtx_runpod = next(
                (
                    gpu
                    for gpu in backend_data["gpus"]
                    if gpu["name"] == "RTX4090" and gpu.get("backend") == "runpod"
                ),
                None,
            )

            assert t4_runpod is not None
            assert t4_aws is not None
            assert rtx_runpod is not None

            assert t4_aws["price"] == {"min": 0.30, "max": 0.60}
            assert t4_aws["count"] == {"min": 1, "max": 4}
            assert t4_runpod["price"] == {"min": 0.25, "max": 0.25}
            assert rtx_runpod["price"] == {"min": 0.65, "max": 0.75}

            response_region = await client.post(
                f"/api/project/{project.name}/gpus/list",
                headers=get_auth_headers(user.token),
                json={"run_spec": run_spec.dict(), "group_by": ["backend", "region"]},
            )
            assert response_region.status_code == 200
            region_data = response_region.json()

            assert len(region_data["gpus"]) == 5

            t4_aws_uswest2 = next(
                (
                    gpu
                    for gpu in region_data["gpus"]
                    if gpu["name"] == "T4"
                    and gpu.get("backend") == "aws"
                    and gpu.get("region") == "us-west-2"
                ),
                None,
            )
            t4_runpod_useast1 = next(
                (
                    gpu
                    for gpu in region_data["gpus"]
                    if gpu["name"] == "T4"
                    and gpu.get("backend") == "runpod"
                    and gpu.get("region") == "us-east-1"
                ),
                None,
            )

            rtx_runpod_useast1 = next(
                (
                    gpu
                    for gpu in region_data["gpus"]
                    if gpu["name"] == "RTX4090"
                    and gpu.get("backend") == "runpod"
                    and gpu.get("region") == "us-east-1"
                ),
                None,
            )
            rtx_runpod_euwest1 = next(
                (
                    gpu
                    for gpu in region_data["gpus"]
                    if gpu["name"] == "RTX4090"
                    and gpu.get("backend") == "runpod"
                    and gpu.get("region") == "eu-west-1"
                ),
                None,
            )

            assert t4_aws_uswest2 is not None
            assert t4_runpod_useast1 is not None
            assert rtx_runpod_useast1 is not None
            assert rtx_runpod_euwest1 is not None

            assert t4_aws_uswest2["backend"] == "aws"
            assert t4_aws_uswest2["region"] == "us-west-2"
            assert t4_aws_uswest2["price"]["min"] == 0.30
            assert t4_aws_uswest2["price"]["max"] == 0.60

            assert t4_runpod_useast1["backend"] == "runpod"
            assert t4_runpod_useast1["region"] == "us-east-1"
            assert t4_runpod_useast1["price"]["min"] == 0.25
            assert t4_runpod_useast1["price"]["max"] == 0.25

            assert rtx_runpod_useast1["backend"] == "runpod"
            assert rtx_runpod_useast1["region"] == "us-east-1"
            assert rtx_runpod_useast1["price"]["min"] == 0.75
            assert rtx_runpod_useast1["price"]["max"] == 0.75

            assert rtx_runpod_euwest1["backend"] == "runpod"
            assert rtx_runpod_euwest1["region"] == "eu-west-1"
            assert rtx_runpod_euwest1["price"]["min"] == 0.65
            assert rtx_runpod_euwest1["price"]["max"] == 0.65
