from datetime import datetime, timedelta, timezone
from textwrap import dedent
from typing import Optional
from unittest.mock import patch

import pytest
from freezegun import freeze_time
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import DevEnvironmentConfiguration
from dstack._internal.core.models.runs import (
    JobProvisioningData,
    JobRuntimeData,
    JobStatus,
    RunStatus,
)
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.models import JobModel, ProjectModel, RunModel, UserModel
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_fleet,
    create_instance,
    create_job,
    create_job_metrics_point,
    create_job_prometheus_metrics,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_auth_headers,
    get_instance_offer_with_availability,
    get_job_provisioning_data,
    get_job_runtime_data,
    get_run_spec,
)

BASE_HTTP_METRICS = b"""
# HELP python_gc_objects_collected_total Objects collected during gc
# TYPE python_gc_objects_collected_total counter
python_gc_objects_collected_total{generation="0"} 13159.0
python_gc_objects_collected_total{generation="1"} 1583.0
python_gc_objects_collected_total{generation="2"} 81.0
# HELP python_gc_objects_uncollectable_total Uncollectable objects found during GC
# TYPE python_gc_objects_uncollectable_total counter
python_gc_objects_uncollectable_total{generation="0"} 0.0
python_gc_objects_uncollectable_total{generation="1"} 0.0
python_gc_objects_uncollectable_total{generation="2"} 0.0
# HELP python_gc_collections_total Number of times this generation was collected
# TYPE python_gc_collections_total counter
python_gc_collections_total{generation="0"} 1609.0
python_gc_collections_total{generation="1"} 146.0
python_gc_collections_total{generation="2"} 9.0
# HELP python_info Python platform information
# TYPE python_info gauge
python_info{implementation="CPython",major="3",minor="12",patchlevel="2",version="3.12.2"} 1.0
# HELP dstack_server_requests_total Total number of HTTP requests
# TYPE dstack_server_requests_total counter
dstack_server_requests_total{endpoint="/metrics",http_status="200",method="GET",project_name="None"} 1.0
# HELP dstack_server_requests_created Total number of HTTP requests
# TYPE dstack_server_requests_created gauge
dstack_server_requests_created{endpoint="/metrics",http_status="200",method="GET",project_name="None"} 1.67262864e+09
# HELP dstack_server_request_duration_seconds HTTP request duration in seconds
# TYPE dstack_server_request_duration_seconds histogram
dstack_server_request_duration_seconds_bucket{endpoint="/metrics",http_status="200",le="0.005",method="GET",project_name="None"} 1.0
dstack_server_request_duration_seconds_bucket{endpoint="/metrics",http_status="200",le="0.01",method="GET",project_name="None"} 1.0
dstack_server_request_duration_seconds_bucket{endpoint="/metrics",http_status="200",le="0.025",method="GET",project_name="None"} 1.0
dstack_server_request_duration_seconds_bucket{endpoint="/metrics",http_status="200",le="0.05",method="GET",project_name="None"} 1.0
dstack_server_request_duration_seconds_bucket{endpoint="/metrics",http_status="200",le="0.075",method="GET",project_name="None"} 1.0
dstack_server_request_duration_seconds_bucket{endpoint="/metrics",http_status="200",le="0.1",method="GET",project_name="None"} 1.0
dstack_server_request_duration_seconds_bucket{endpoint="/metrics",http_status="200",le="0.25",method="GET",project_name="None"} 1.0
dstack_server_request_duration_seconds_bucket{endpoint="/metrics",http_status="200",le="0.5",method="GET",project_name="None"} 1.0
dstack_server_request_duration_seconds_bucket{endpoint="/metrics",http_status="200",le="0.75",method="GET",project_name="None"} 1.0
dstack_server_request_duration_seconds_bucket{endpoint="/metrics",http_status="200",le="1.0",method="GET",project_name="None"} 1.0
dstack_server_request_duration_seconds_bucket{endpoint="/metrics",http_status="200",le="2.5",method="GET",project_name="None"} 1.0
dstack_server_request_duration_seconds_bucket{endpoint="/metrics",http_status="200",le="5.0",method="GET",project_name="None"} 1.0
dstack_server_request_duration_seconds_bucket{endpoint="/metrics",http_status="200",le="7.5",method="GET",project_name="None"} 1.0
dstack_server_request_duration_seconds_bucket{endpoint="/metrics",http_status="200",le="10.0",method="GET",project_name="None"} 1.0
dstack_server_request_duration_seconds_bucket{endpoint="/metrics",http_status="200",le="+Inf",method="GET",project_name="None"} 1.0
dstack_server_request_duration_seconds_count{endpoint="/metrics",http_status="200",method="GET",project_name="None"} 1.0
dstack_server_request_duration_seconds_sum{endpoint="/metrics",http_status="200",method="GET",project_name="None"} 0.0
# HELP dstack_server_request_duration_seconds_created HTTP request duration in seconds
# TYPE dstack_server_request_duration_seconds_created gauge
dstack_server_request_duration_seconds_created{endpoint="/metrics",http_status="200",method="GET",project_name="None"} 1.67262864e+09
"""


@pytest.fixture
def enable_metrics(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("dstack._internal.server.settings.ENABLE_PROMETHEUS_METRICS", True)
    monkeypatch.setattr("dstack._internal.server.routers.prometheus._auth._token", None)


FAKE_NOW = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)


@freeze_time(FAKE_NOW)
@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("image_config_mock", "test_db", "enable_metrics")
class TestGetPrometheusMetrics:
    @patch("prometheus_client.generate_latest", lambda: BASE_HTTP_METRICS)
    async def test_returns_metrics(self, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, name="test-user", global_role=GlobalRole.USER)
        offer = get_instance_offer_with_availability(
            instance_type="test-type",
            cpu_count=32,
            memory_gib=128,
            gpu_count=2,
            gpu_name="V4",
            gpu_memory_gib=16,
            price=12,
        )
        project_2 = await _create_project(session, "project-2", user)
        jpd_2_1 = get_job_provisioning_data(
            backend=BackendType.AWS,
            cpu_count=16,
            memory_gib=64,
            gpu_name="T4",
            gpu_count=2,
            price=16,
        )
        job_2_1 = await _create_job(
            session=session,
            run_name="run-1",
            project=project_2,
            user=user,
            status=JobStatus.RUNNING,
            job_provisioning_data=jpd_2_1,
            submitted_at=FAKE_NOW - timedelta(seconds=100),
        )
        await create_job_prometheus_metrics(
            session=session,
            job=job_2_1,
            text=dedent("""
                # HELP FIELD_1 Test field 1
                # TYPE FIELD_1 gauge
                FIELD_1{gpu="0"} 100
                FIELD_1{gpu="1"} 200
            """),
        )
        project_1 = await _create_project(session, "project-1", user)
        # jrd.offer.instance.resources has higher priority than jpd.instance_type.resources,
        # should be ignored
        jpd_1_1 = get_job_provisioning_data(backend=BackendType.AWS, gpu_count=4, gpu_name="T4")
        jrd_1_1 = get_job_runtime_data(offer=offer)
        job_1_1 = await _create_job(
            session=session,
            run_name="run-1",
            project=project_1,
            user=user,
            status=JobStatus.RUNNING,
            job_provisioning_data=jpd_1_1,
            job_runtime_data=jrd_1_1,
            submitted_at=FAKE_NOW - timedelta(seconds=120),
        )
        await create_job_prometheus_metrics(
            session=session,
            job=job_1_1,
            text=dedent("""
                # Comments should be skipped

                # HELP FIELD_1 Test field 1
                # TYPE FIELD_1 gauge
                FIELD_1{gpu="0"} 350
                FIELD_1{gpu="1"} 400

                # HELP FIELD_2 Test field 2
                # TYPE FIELD_2 counter
                FIELD_2{gpu="0"} 337325 1395066363000
                FIELD_2{gpu="1"} 987169 1395066363010
            """),
        )
        await create_job_metrics_point(
            session=session,
            job_model=job_1_1,
            timestamp=FAKE_NOW - timedelta(seconds=30),
            cpu_usage_micro=3_500_000,
            memory_working_set_bytes=3_221_225_472,
            memory_usage_bytes=4_294_967_296,
            gpus_util_percent=[80, 90],
            gpus_memory_usage_bytes=[1_073_741_824, 2_147_483_648],
        )
        # Older, ignored
        await create_job_metrics_point(
            session=session,
            job_model=job_1_1,
            timestamp=FAKE_NOW - timedelta(seconds=60),
            cpu_usage_micro=2_000_000,
            memory_working_set_bytes=1_073_741_824,
            memory_usage_bytes=2_147_483_648,
        )
        jpd_1_2 = get_job_provisioning_data(
            backend=BackendType.AWS,
            cpu_count=24,
            memory_gib=224,
            gpu_count=3,
            gpu_name="L4",
            price=12.5,
        )
        job_1_2 = await _create_job(
            session=session,
            run_name="run-2",
            project=project_1,
            user=user,
            status=JobStatus.RUNNING,
            job_provisioning_data=jpd_1_2,
            submitted_at=FAKE_NOW - timedelta(seconds=150),
        )

        await create_job_prometheus_metrics(
            session=session,
            job=job_1_2,
            text=dedent("""
                # HELP FIELD_1 Test field 1
                # TYPE FIELD_1 gauge
                FIELD_1{gpu="0"} 1200.0
                FIELD_1{gpu="1"} 1600.0
                FIELD_1{gpu="2"} 2400.0
            """),
        )
        # Terminated job, should not appear in the response
        job_1_3 = await _create_job(session, "run-3", project_1, user, JobStatus.TERMINATED)
        await create_job_prometheus_metrics(
            session=session,
            job=job_1_3,
            text=dedent("""
                # HELP FIELD_1 Test field 1
                # TYPE FIELD_1 gauge
                FIELD_1{gpu="0"} 10
                FIELD_1{gpu="1"} 20
            """),
        )
        await _create_run(session, "done", project_1, user, RunStatus.DONE)
        other_user = await create_user(
            session=session, name="other-user", global_role=GlobalRole.USER
        )
        await add_project_member(
            session=session, project=project_2, user=other_user, project_role=ProjectRole.USER
        )
        await _create_run(session, "failed-1", project_2, other_user, RunStatus.FAILED)
        await _create_run(session, "failed-2", project_2, other_user, RunStatus.FAILED)
        fleet = await create_fleet(session=session, project=project_1, name="test-fleet")
        instance = await create_instance(
            session=session,
            project=project_1,
            fleet=fleet,
            backend=BackendType.AWS,
            offer=offer,
            price=14,
            created_at=FAKE_NOW - timedelta(hours=1),
            name="test-instance",
        )

        response = await client.get("/metrics")

        assert response.status_code == 200
        expected = (
            dedent(f"""\
            # HELP dstack_instance_duration_seconds_total Total seconds the instance is running
            # TYPE dstack_instance_duration_seconds_total counter
            dstack_instance_duration_seconds_total{{dstack_project_name="project-1",dstack_fleet_name="test-fleet",dstack_fleet_id="{fleet.id}",dstack_instance_name="test-instance",dstack_instance_id="{instance.id}",dstack_instance_type="test-type",dstack_backend="aws",dstack_gpu="V4"}} 3600.0
            # HELP dstack_instance_price_dollars_per_hour Instance price, USD/hour
            # TYPE dstack_instance_price_dollars_per_hour gauge
            dstack_instance_price_dollars_per_hour{{dstack_project_name="project-1",dstack_fleet_name="test-fleet",dstack_fleet_id="{fleet.id}",dstack_instance_name="test-instance",dstack_instance_id="{instance.id}",dstack_instance_type="test-type",dstack_backend="aws",dstack_gpu="V4"}} 14.0
            # HELP dstack_instance_gpu_count Instance GPU count
            # TYPE dstack_instance_gpu_count gauge
            dstack_instance_gpu_count{{dstack_project_name="project-1",dstack_fleet_name="test-fleet",dstack_fleet_id="{fleet.id}",dstack_instance_name="test-instance",dstack_instance_id="{instance.id}",dstack_instance_type="test-type",dstack_backend="aws",dstack_gpu="V4"}} 2.0
            # HELP dstack_run_count_total Total runs count
            # TYPE dstack_run_count_total counter
            dstack_run_count_total{{dstack_project_name="project-1",dstack_user_name="test-user"}} 4.0
            dstack_run_count_total{{dstack_project_name="project-2",dstack_user_name="other-user"}} 2.0
            dstack_run_count_total{{dstack_project_name="project-2",dstack_user_name="test-user"}} 1.0
            # HELP dstack_run_count_terminated_total Terminated runs count
            # TYPE dstack_run_count_terminated_total counter
            dstack_run_count_terminated_total{{dstack_project_name="project-1",dstack_user_name="test-user"}} 0.0
            dstack_run_count_terminated_total{{dstack_project_name="project-2",dstack_user_name="other-user"}} 0.0
            dstack_run_count_terminated_total{{dstack_project_name="project-2",dstack_user_name="test-user"}} 0.0
            # HELP dstack_run_count_failed_total Failed runs count
            # TYPE dstack_run_count_failed_total counter
            dstack_run_count_failed_total{{dstack_project_name="project-1",dstack_user_name="test-user"}} 0.0
            dstack_run_count_failed_total{{dstack_project_name="project-2",dstack_user_name="other-user"}} 2.0
            dstack_run_count_failed_total{{dstack_project_name="project-2",dstack_user_name="test-user"}} 0.0
            # HELP dstack_run_count_done_total Done runs count
            # TYPE dstack_run_count_done_total counter
            dstack_run_count_done_total{{dstack_project_name="project-1",dstack_user_name="test-user"}} 1.0
            dstack_run_count_done_total{{dstack_project_name="project-2",dstack_user_name="other-user"}} 0.0
            dstack_run_count_done_total{{dstack_project_name="project-2",dstack_user_name="test-user"}} 0.0
            # HELP dstack_job_duration_seconds_total Total seconds the job is running
            # TYPE dstack_job_duration_seconds_total counter
            dstack_job_duration_seconds_total{{dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_1_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_1_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="V4"}} 120.0
            dstack_job_duration_seconds_total{{dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-2",dstack_run_id="{job_1_2.run_id}",dstack_job_name="run-2-0-0",dstack_job_id="{job_1_2.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="L4"}} 150.0
            dstack_job_duration_seconds_total{{dstack_project_name="project-2",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_2_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_2_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="T4"}} 100.0
            # HELP dstack_job_price_dollars_per_hour Job instance price, USD/hour
            # TYPE dstack_job_price_dollars_per_hour gauge
            dstack_job_price_dollars_per_hour{{dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_1_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_1_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="V4"}} 12.0
            dstack_job_price_dollars_per_hour{{dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-2",dstack_run_id="{job_1_2.run_id}",dstack_job_name="run-2-0-0",dstack_job_id="{job_1_2.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="L4"}} 12.5
            dstack_job_price_dollars_per_hour{{dstack_project_name="project-2",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_2_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_2_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="T4"}} 16.0
            # HELP dstack_job_gpu_count Job GPU count
            # TYPE dstack_job_gpu_count gauge
            dstack_job_gpu_count{{dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_1_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_1_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="V4"}} 2.0
            dstack_job_gpu_count{{dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-2",dstack_run_id="{job_1_2.run_id}",dstack_job_name="run-2-0-0",dstack_job_id="{job_1_2.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="L4"}} 3.0
            dstack_job_gpu_count{{dstack_project_name="project-2",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_2_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_2_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="T4"}} 2.0
            # HELP dstack_job_cpu_count Job CPU count
            # TYPE dstack_job_cpu_count gauge
            dstack_job_cpu_count{{dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_1_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_1_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="V4"}} 32.0
            dstack_job_cpu_count{{dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-2",dstack_run_id="{job_1_2.run_id}",dstack_job_name="run-2-0-0",dstack_job_id="{job_1_2.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="L4"}} 24.0
            dstack_job_cpu_count{{dstack_project_name="project-2",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_2_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_2_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="T4"}} 16.0
            # HELP dstack_job_cpu_time_seconds_total Total CPU time consumed by the job, seconds
            # TYPE dstack_job_cpu_time_seconds_total counter
            dstack_job_cpu_time_seconds_total{{dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_1_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_1_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="V4"}} 3.5
            # HELP dstack_job_memory_total_bytes Total memory allocated for the job, bytes
            # TYPE dstack_job_memory_total_bytes gauge
            dstack_job_memory_total_bytes{{dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_1_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_1_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="V4"}} 137438953472.0
            dstack_job_memory_total_bytes{{dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-2",dstack_run_id="{job_1_2.run_id}",dstack_job_name="run-2-0-0",dstack_job_id="{job_1_2.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="L4"}} 240518168576.0
            dstack_job_memory_total_bytes{{dstack_project_name="project-2",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_2_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_2_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="T4"}} 68719476736.0
            # HELP dstack_job_memory_usage_bytes Memory used by the job (including cache), bytes
            # TYPE dstack_job_memory_usage_bytes gauge
            dstack_job_memory_usage_bytes{{dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_1_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_1_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="V4"}} 4294967296.0
            # HELP dstack_job_memory_working_set_bytes Memory used by the job (not including cache), bytes
            # TYPE dstack_job_memory_working_set_bytes gauge
            dstack_job_memory_working_set_bytes{{dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_1_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_1_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="V4"}} 3221225472.0
            # HELP dstack_job_gpu_usage_ratio Job GPU usage, percent (as 0.0-1.0)
            # TYPE dstack_job_gpu_usage_ratio gauge
            dstack_job_gpu_usage_ratio{{dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_1_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_1_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="V4",dstack_gpu_num="0"}} 0.8
            dstack_job_gpu_usage_ratio{{dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_1_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_1_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="V4",dstack_gpu_num="1"}} 0.9
            # HELP dstack_job_gpu_memory_total_bytes Total GPU memory allocated for the job, bytes
            # TYPE dstack_job_gpu_memory_total_bytes gauge
            dstack_job_gpu_memory_total_bytes{{dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_1_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_1_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="V4",dstack_gpu_num="0"}} 17179869184.0
            dstack_job_gpu_memory_total_bytes{{dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_1_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_1_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="V4",dstack_gpu_num="1"}} 17179869184.0
            # HELP dstack_job_gpu_memory_usage_bytes GPU memory used by the job, bytes
            # TYPE dstack_job_gpu_memory_usage_bytes gauge
            dstack_job_gpu_memory_usage_bytes{{dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_1_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_1_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="V4",dstack_gpu_num="0"}} 1073741824.0
            dstack_job_gpu_memory_usage_bytes{{dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_1_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_1_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="V4",dstack_gpu_num="1"}} 2147483648.0
            # HELP FIELD_1 Test field 1
            # TYPE FIELD_1 gauge
            FIELD_1{{gpu="0",dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_1_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_1_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="V4"}} 350.0
            FIELD_1{{gpu="1",dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_1_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_1_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="V4"}} 400.0
            FIELD_1{{gpu="0",dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-2",dstack_run_id="{job_1_2.run_id}",dstack_job_name="run-2-0-0",dstack_job_id="{job_1_2.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="L4"}} 1200.0
            FIELD_1{{gpu="1",dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-2",dstack_run_id="{job_1_2.run_id}",dstack_job_name="run-2-0-0",dstack_job_id="{job_1_2.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="L4"}} 1600.0
            FIELD_1{{gpu="2",dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-2",dstack_run_id="{job_1_2.run_id}",dstack_job_name="run-2-0-0",dstack_job_id="{job_1_2.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="L4"}} 2400.0
            FIELD_1{{gpu="0",dstack_project_name="project-2",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_2_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_2_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="T4"}} 100.0
            FIELD_1{{gpu="1",dstack_project_name="project-2",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_2_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_2_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="T4"}} 200.0
            # HELP FIELD_2 Test field 2
            # TYPE FIELD_2 counter
            FIELD_2{{gpu="0",dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_1_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_1_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="V4"}} 337325.0 1395066363000
            FIELD_2{{gpu="1",dstack_project_name="project-1",dstack_user_name="test-user",dstack_run_name="run-1",dstack_run_id="{job_1_1.run_id}",dstack_job_name="run-1-0-0",dstack_job_id="{job_1_1.id}",dstack_job_num="0",dstack_replica_num="0",dstack_run_type="dev-environment",dstack_backend="aws",dstack_gpu="V4"}} 987169.0 1395066363010
        """)
            + "\n"
            + BASE_HTTP_METRICS.decode().strip()
        )
        assert response.text.strip() == expected

    @patch("prometheus_client.generate_latest", lambda: BASE_HTTP_METRICS)
    async def test_returns_empty_response_if_no_runs(self, client: AsyncClient):
        response = await client.get("/metrics")
        assert response.status_code == 200
        assert response.text.strip() == BASE_HTTP_METRICS.decode().strip()

    async def test_returns_404_if_not_enabled(
        self, monkeypatch: pytest.MonkeyPatch, client: AsyncClient
    ):
        monkeypatch.setattr("dstack._internal.server.settings.ENABLE_PROMETHEUS_METRICS", False)
        response = await client.get("/metrics")
        assert response.status_code == 404

    @pytest.mark.parametrize("token", [None, "foo"])
    async def test_returns_403_if_not_authenticated(
        self, monkeypatch: pytest.MonkeyPatch, client: AsyncClient, token: Optional[str]
    ):
        monkeypatch.setattr("dstack._internal.server.routers.prometheus._auth._token", "secret")
        if token is not None:
            headers = get_auth_headers(token)
        else:
            headers = None
        response = await client.get("/metrics", headers=headers)
        assert response.status_code == 403

    async def test_returns_200_if_token_is_valid(
        self, monkeypatch: pytest.MonkeyPatch, client: AsyncClient
    ):
        monkeypatch.setattr("dstack._internal.server.routers.prometheus._auth._token", "secret")
        response = await client.get("/metrics", headers=get_auth_headers("secret"))
        assert response.status_code == 200


async def _create_project(session: AsyncSession, name: str, user: UserModel) -> ProjectModel:
    project = await create_project(session=session, owner=user, name=name)
    await add_project_member(
        session=session, project=project, user=user, project_role=ProjectRole.USER
    )
    return project


async def _create_run(
    session: AsyncSession,
    run_name: str,
    project: ProjectModel,
    user: UserModel,
    status: RunStatus,
    submitted_at: datetime = FAKE_NOW,
) -> RunModel:
    repo = await create_repo(session=session, project_id=project.id, repo_name=f"{run_name}-repo")
    configuration = DevEnvironmentConfiguration(ide="vscode")
    run_spec = get_run_spec(run_name=run_name, repo_id=repo.name, configuration=configuration)
    return await create_run(
        session=session,
        project=project,
        repo=repo,
        user=user,
        run_name=run_name,
        run_spec=run_spec,
        status=status,
        submitted_at=submitted_at,
    )


async def _create_job(
    session: AsyncSession,
    run_name: str,
    project: ProjectModel,
    user: UserModel,
    status: JobStatus,
    job_provisioning_data: Optional[JobProvisioningData] = None,
    job_runtime_data: Optional[JobRuntimeData] = None,
    submitted_at: datetime = FAKE_NOW,
) -> JobModel:
    run = await _create_run(
        session=session,
        run_name=run_name,
        project=project,
        user=user,
        status=RunStatus.SUBMITTED,
        submitted_at=submitted_at,
    )
    job = await create_job(
        session=session,
        run=run,
        status=status,
        job_provisioning_data=job_provisioning_data,
        job_runtime_data=job_runtime_data,
        submitted_at=submitted_at,
    )
    return job
