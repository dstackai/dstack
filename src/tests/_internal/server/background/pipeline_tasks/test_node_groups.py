from datetime import datetime, timezone
from uuid import uuid4

import pytest

from dstack._internal.core.models.runs import Job, JobSpec, JobSubmission
from dstack._internal.server.background.pipeline_tasks.jobs_running import (
    _build_nodes_ip_view,
    _get_cluster_info,
    _referenced_ips_ready,
)
from dstack._internal.server.testing.common import get_job_provisioning_data
from dstack._internal.utils.interpolator import InterpolatorError


def _job(
    *,
    job_num: int,
    node_group_index: int,
    node_group_job_index: int,
    internal_ip: str,
    gpu_count: int,
) -> Job:
    return Job.model_construct(
        job_spec=JobSpec.model_construct(
            replica_num=0,
            job_num=job_num,
            node_group_index=node_group_index,
            node_group_job_index=node_group_job_index,
            commands=[],
        ),
        job_submissions=[
            JobSubmission.model_construct(
                id=uuid4(),
                submitted_at=datetime.now(timezone.utc),
                job_provisioning_data=get_job_provisioning_data(
                    internal_ip=internal_ip,
                    gpu_count=gpu_count,
                ),
                job_runtime_data=None,
            )
        ],
    )


class TestGetClusterInfo:
    def test_fills_gpus_per_node(self):
        jobs = [
            _job(
                job_num=0,
                node_group_index=0,
                node_group_job_index=0,
                internal_ip="10.0.0.1",
                gpu_count=8,
            ),
            _job(
                job_num=1,
                node_group_index=1,
                node_group_job_index=0,
                internal_ip="10.0.0.2",
                gpu_count=4,
            ),
        ]
        this_jpd = get_job_provisioning_data(internal_ip="10.0.0.1", gpu_count=8)
        info = _get_cluster_info(
            jobs=jobs,
            replica_num=0,
            job_provisioning_data=this_jpd,
            job_runtime_data=None,
        )
        assert info.job_ips == ["10.0.0.1", "10.0.0.2"]
        assert info.master_job_ip == "10.0.0.1"
        assert info.gpus_per_job == 8
        assert info.gpus_per_node == [8, 4]


class TestNodesIpView:
    def test_builds_group_view(self):
        jobs = [
            _job(
                job_num=0,
                node_group_index=0,
                node_group_job_index=0,
                internal_ip="10.0.0.1",
                gpu_count=1,
            ),
            _job(
                job_num=1,
                node_group_index=0,
                node_group_job_index=1,
                internal_ip="10.0.0.2",
                gpu_count=1,
            ),
            _job(
                job_num=2,
                node_group_index=1,
                node_group_job_index=0,
                internal_ip="10.0.0.3",
                gpu_count=1,
            ),
        ]
        assert _build_nodes_ip_view(jobs, replica_num=0) == [
            ["10.0.0.1", "10.0.0.2"],
            ["10.0.0.3"],
        ]

    def test_referenced_ips_ready(self):
        nodes_view = [["10.0.0.1"], [""]]
        assert _referenced_ips_ready(["echo ${{ groups[0].nodes[0].IP_ADDRESS }}"], nodes_view)
        assert not _referenced_ips_ready(["echo ${{ groups[1].nodes[0].IP_ADDRESS }}"], nodes_view)

    def test_referenced_ips_out_of_range(self):
        nodes_view = [["10.0.0.1"]]
        with pytest.raises(InterpolatorError, match="out of range"):
            _referenced_ips_ready(["echo ${{ groups[1].nodes[0].IP_ADDRESS }}"], nodes_view)
