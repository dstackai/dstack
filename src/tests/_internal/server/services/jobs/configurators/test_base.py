from typing import Union

import pytest

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.volumes import InstanceMountPoint, MountPoint, VolumeMountPoint
from dstack._internal.server.services.jobs.configurators.base import interpolate_job_volumes


class TestInterpolateJobVolumes:
    @pytest.mark.parametrize(
        ["run_volumes", "job_num", "job_volumes"],
        [
            pytest.param(
                [VolumeMountPoint(name="volume", path="/volume")],
                0,
                [VolumeMountPoint(name=["volume"], path="/volume")],
                id="no_interpolation",
            ),
            pytest.param(
                [InstanceMountPoint(instance_path="/volume", path="/volume")],
                0,
                [InstanceMountPoint(instance_path="/volume", path="/volume")],
                id="instance_mount",
            ),
            pytest.param(
                [
                    VolumeMountPoint(
                        name="job${{dstack.job_num}}-rank${{dstack.node_rank}}", path="/volume"
                    )
                ],
                2,
                [VolumeMountPoint(name=["job2-rank2"], path="/volume")],
                id="job_num_and_node_rank",
            ),
        ],
    )
    def test_interpolates_volumes(
        self,
        run_volumes: list[Union[MountPoint, str]],
        job_num: int,
        job_volumes: list[MountPoint],
    ):
        assert interpolate_job_volumes(run_volumes, job_num) == job_volumes

    @pytest.mark.parametrize(
        ["run_volumes", "job_num"],
        [
            pytest.param(
                [VolumeMountPoint(name="${{}", path="/volume")],
                0,
                id="invalid_syntax",
            ),
            pytest.param(
                [VolumeMountPoint(name="${{ unknown.namespace }}", path="/volume")],
                0,
                id="unknown_namespace",
            ),
            pytest.param(
                [VolumeMountPoint(name="${{ dstack.var }}", path="/volume")],
                0,
                id="unknown_var",
            ),
        ],
    )
    def test_raises_server_client_error(
        self,
        run_volumes: list[Union[MountPoint, str]],
        job_num: int,
    ):
        with pytest.raises(ServerClientError):
            assert interpolate_job_volumes(run_volumes, job_num)
