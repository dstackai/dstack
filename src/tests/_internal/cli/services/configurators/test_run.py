import argparse
from datetime import datetime, timezone
from textwrap import dedent
from typing import List, Optional, Tuple
from unittest.mock import Mock

import pytest
from gpuhunt import AcceleratorVendor

from dstack._internal.cli.services.configurators import get_run_configurator_class
from dstack._internal.cli.services.configurators.run import (
    BaseRunConfigurator,
    _get_apply_status,
    _get_apply_wait_renderables,
    render_run_spec_diff,
)
from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import RegistryAuth
from dstack._internal.core.models.configurations import (
    BaseRunConfiguration,
    DevEnvironmentConfiguration,
    PortMapping,
    ScalingSpec,
    ServiceConfiguration,
    TaskConfiguration,
)
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.resources import Range
from dstack._internal.core.models.runs import RunStatus, ServiceSpec
from dstack._internal.server.services import encryption  # noqa: F401  # import for side-effect
from dstack._internal.server.services.runs import run_model_to_run
from dstack._internal.server.testing.common import (
    create_project,
    create_repo,
    create_run,
    create_user,
    get_run_spec,
)
from dstack.api import Run
from dstack.api.server import APIClient


class TestApplyArgs:
    def apply_args(
        self, conf: BaseRunConfiguration, args: List[str]
    ) -> Tuple[BaseRunConfiguration, argparse.Namespace]:
        parser = argparse.ArgumentParser()
        configurator_class = get_run_configurator_class(conf.type)
        configurator = configurator_class(Mock())
        configurator.register_args(parser)
        conf = conf.copy(deep=True)  # to avoid modifying the original configuration
        parsed_args = parser.parse_args(args)
        configurator.apply_args(conf, parsed_args)
        return conf, parsed_args

    def test_env(self):
        conf = TaskConfiguration(commands=["whoami"])
        modified, args = self.apply_args(conf, ["-e", "A=1", "--env", "B=2"])
        conf.env = Env.parse_obj({"A": "1", "B": "2"})
        assert modified.dict() == conf.dict()

    def test_ports(self):
        conf = TaskConfiguration(commands=["whoami"])
        modified, args = self.apply_args(conf, ["-p", "80", "--port", "8080"])
        conf.ports = [
            PortMapping(local_port=80, container_port=80),
            PortMapping(local_port=8080, container_port=8080),
        ]
        assert modified.dict() == conf.dict()

    def test_container_ports_conflict(self):
        conf = TaskConfiguration(commands=["whoami"])
        with pytest.raises(ConfigurationError):
            self.apply_args(conf, ["-p", "8000:80", "--port", "8001:80"])

    def test_env_override(self):
        conf = TaskConfiguration(commands=["whoami"], env=Env.parse_obj({"A": "0"}))
        modified, args = self.apply_args(conf, ["-e", "A=1", "--env", "B=2"])
        conf.env = Env.parse_obj({"A": "1", "B": "2"})
        assert modified.dict() == conf.dict()

    def test_ports_override(self):
        conf = TaskConfiguration(commands=["whoami"], ports=["80"])
        modified, args = self.apply_args(conf, ["-p", "8000:80", "--port", "8001:8000"])
        conf.ports = [
            PortMapping(local_port=8000, container_port=80),
            PortMapping(local_port=8001, container_port=8000),
        ]
        assert modified.dict() == conf.dict()

    def test_local_ports_conflict(self):
        conf = TaskConfiguration(commands=["whoami"], ports=["3000"])
        with pytest.raises(ConfigurationError):
            self.apply_args(conf, ["-p", "3000:4000"])

    def test_any_port(self):
        conf = TaskConfiguration(commands=["whoami"], ports=["8000"])
        modified, args = self.apply_args(conf, ["-p", "*:8000"])
        conf.ports = [PortMapping(local_port=None, container_port=8000)]
        assert modified.dict() == conf.dict()

    def test_interpolates_env(self):
        conf = TaskConfiguration(
            image="my_image",
            registry_auth=RegistryAuth(
                username="${{ env.REGISTRY_USERNAME }}",
                password="${{ env.REGISTRY_PASSWORD }}",
            ),
            env=Env.parse_obj(
                {
                    "REGISTRY_USERNAME": "test_user",
                    "REGISTRY_PASSWORD": "test_password",
                }
            ),
        )
        modified, args = self.apply_args(conf, [])
        assert modified.registry_auth == RegistryAuth(
            username="test_user",
            password="test_password",
        )


class TestValidateGPUVendorAndImage:
    def prepare_conf(
        self,
        *,
        image: Optional[str] = None,
        gpu_spec: Optional[str] = None,
        docker: Optional[bool] = None,
    ) -> BaseRunConfiguration:
        conf_dict = {
            "type": "none",
        }
        if image is not None:
            conf_dict["image"] = image
        if gpu_spec is not None:
            conf_dict["resources"] = {
                "gpu": gpu_spec,
            }
        if docker is not None:
            conf_dict["docker"] = docker
        return BaseRunConfiguration.parse_obj(conf_dict)

    def validate(self, conf: BaseRunConfiguration) -> None:
        BaseRunConfigurator(api_client=Mock()).validate_gpu_vendor_and_image(conf)

    def test_no_gpu(self):
        conf = self.prepare_conf()
        self.validate(conf)
        assert conf.resources.gpu is not None
        # Vendor is not written to spec for compatibility with older servers.
        # The server infers nvidia in set_resources_defaults().
        assert conf.resources.gpu.vendor is None
        assert conf.resources.gpu.name is None
        assert conf.resources.gpu.count.min == 0

    def test_zero_gpu(self):
        conf = self.prepare_conf(gpu_spec="0")
        self.validate(conf)
        assert conf.resources.gpu.vendor is None

    def test_gpu_no_vendor_no_image_defaults_to_nvidia(self):
        """Vendor is inferred as nvidia for validation but NOT written to spec."""
        conf = self.prepare_conf(gpu_spec="1")
        self.validate(conf)
        assert conf.resources.gpu.vendor is None

    def test_gpu_no_vendor_with_image_no_default(self):
        conf = self.prepare_conf(gpu_spec="1", image="my-custom-image")
        self.validate(conf)
        assert conf.resources.gpu.vendor is None

    def test_gpu_no_vendor_docker_true_no_default(self):
        conf = self.prepare_conf(gpu_spec="1", docker=True)
        self.validate(conf)
        assert conf.resources.gpu.vendor is None

    @pytest.mark.parametrize(
        ["gpu_spec", "expected_vendor"],
        [
            ["nvidia", AcceleratorVendor.NVIDIA],
            ["tpu", AcceleratorVendor.GOOGLE],
            ["google", AcceleratorVendor.GOOGLE],
        ],
    )
    def test_non_amd_vendor_declared(self, gpu_spec, expected_vendor):
        conf = self.prepare_conf(gpu_spec=gpu_spec)
        self.validate(conf)
        assert conf.resources.gpu.vendor == expected_vendor

    def test_amd_vendor_declared_with_image(self):
        conf = self.prepare_conf(image="tgi:rocm", gpu_spec="AMD")
        self.validate(conf)
        assert conf.resources.gpu.vendor == AcceleratorVendor.AMD

    @pytest.mark.parametrize(
        ["gpu_spec", "expected_vendor"],
        [
            ["a40,l40", AcceleratorVendor.NVIDIA],  # lowercase
            ["V3-64", AcceleratorVendor.GOOGLE],  # uppercase
        ],
    )
    def test_one_non_amd_vendor_inferred(self, gpu_spec, expected_vendor):
        conf = self.prepare_conf(gpu_spec=gpu_spec)
        self.validate(conf)
        assert conf.resources.gpu.vendor == expected_vendor

    @pytest.mark.parametrize("gpu_spec", ["MI300X", "MI300x", "mi300x"])
    def test_amd_vendor_inferred_with_image(self, gpu_spec):
        conf = self.prepare_conf(image="tgi:rocm", gpu_spec=gpu_spec)
        self.validate(conf)
        assert conf.resources.gpu.vendor == AcceleratorVendor.AMD

    @pytest.mark.parametrize("gpu_spec", ["foo", "foo,bar"])
    def test_one_unknown_vendor_inferred(self, gpu_spec):
        conf = self.prepare_conf(gpu_spec=gpu_spec)
        self.validate(conf)
        assert conf.resources.gpu.vendor is None

    @pytest.mark.parametrize(
        "gpu_spec",
        [
            "A1000,v4",  # Nvidia and Google
            "v3-64,foo",  # Google and unknown
        ],
    )
    def test_two_non_amd_vendors_inferred(self, gpu_spec):
        conf = self.prepare_conf(gpu_spec=gpu_spec)
        self.validate(conf)
        assert conf.resources.gpu.vendor is None

    @pytest.mark.parametrize(
        "gpu_spec",
        [
            "A1000,mi300x",  # Nvidia and AMD (lowercase)
            "MI300x,v3-64",  # AMD (mixedcase) and Google
            "foo,MI300X",  # unknown and AMD (uppercase)
        ],
    )
    def test_two_vendors_including_amd_inferred_with_image(self, gpu_spec):
        conf = self.prepare_conf(image="tgi:rocm", gpu_spec=gpu_spec)
        self.validate(conf)
        assert conf.resources.gpu.vendor is None

    def test_amd_vendor_declared_no_image(self):
        conf = self.prepare_conf(gpu_spec="AMD")
        with pytest.raises(
            ConfigurationError, match=r"`image` is required if `resources.gpu.vendor` is `amd`"
        ):
            self.validate(conf)

    @pytest.mark.parametrize("gpu_spec", ["AMD", "MI300X"])
    def test_amd_vendor_docker_true_no_image(self, gpu_spec):
        conf = self.prepare_conf(gpu_spec=gpu_spec, docker=True)
        self.validate(conf)
        assert conf.resources.gpu.vendor == AcceleratorVendor.AMD

    @pytest.mark.parametrize("gpu_spec", ["MI300X", "MI300x", "mi300x"])
    def test_amd_vendor_inferred_no_image(self, gpu_spec):
        conf = self.prepare_conf(gpu_spec=gpu_spec)
        with pytest.raises(
            ConfigurationError, match=r"`image` is required if `resources.gpu.vendor` is `amd`"
        ):
            self.validate(conf)

    @pytest.mark.parametrize(
        "gpu_spec",
        [
            "A1000,mi300x",  # Nvidia and AMD (lowercase)
            "MI300x,v3-64",  # AMD (mixedcase) and Google
            "foo,MI300X",  # unknown and AMD (uppercase)
        ],
    )
    def test_two_vendors_including_amd_inferred_no_image(self, gpu_spec):
        conf = self.prepare_conf(gpu_spec=gpu_spec)
        with pytest.raises(
            ConfigurationError, match=r"`image` is required if `resources.gpu.vendor` is `amd`"
        ):
            self.validate(conf)

    @pytest.mark.parametrize("gpu_spec", ["n150", "n300"])
    def test_tenstorrent_docker_true_no_image(self, gpu_spec):
        conf = self.prepare_conf(gpu_spec=gpu_spec, docker=True)
        self.validate(conf)
        assert conf.resources.gpu.vendor == AcceleratorVendor.TENSTORRENT


class TestValidateCPUArchAndImage:
    def prepare_conf(
        self,
        *,
        cpu_spec: str,
        gpu_spec: Optional[str] = None,
        image: Optional[str] = None,
    ) -> BaseRunConfiguration:
        conf_dict = {
            "type": "none",
            "resources": {
                "cpu": cpu_spec,
            },
        }
        if image is not None:
            conf_dict["image"] = image
        if gpu_spec is not None:
            conf_dict["resources"]["gpu"] = gpu_spec
        return BaseRunConfiguration.parse_obj(conf_dict)

    def validate(self, conf: BaseRunConfiguration) -> None:
        # validate_gpu_vendor_and_image sets GPU vendor if not set
        BaseRunConfigurator(api_client=Mock()).validate_gpu_vendor_and_image(conf)
        BaseRunConfigurator(api_client=Mock()).validate_cpu_arch_and_image(conf)

    @pytest.mark.parametrize("gpu_spec", [None, "GH200", "H100"])
    def test_explicit_arm_with_image(self, gpu_spec: Optional[str]):
        conf = self.prepare_conf(cpu_spec="arm:1..", gpu_spec=gpu_spec, image="ubuntu")
        self.validate(conf)

    def test_inferred_arm_with_image(self):
        conf = self.prepare_conf(cpu_spec="1..", gpu_spec="GH200", image="ubuntu")
        self.validate(conf)

    @pytest.mark.parametrize("cpu_spec", ["1..", "arm:1.."])
    def test_arm_no_image(self, cpu_spec: str):
        conf = self.prepare_conf(cpu_spec=cpu_spec, gpu_spec="GH200")
        with pytest.raises(
            ConfigurationError, match=r"`image` is required if `resources.cpu.arch` is `arm`"
        ):
            self.validate(conf)

    @pytest.mark.parametrize("cpu_spec", ["1..", "x86:1.."])
    @pytest.mark.parametrize("image", [None, "ubuntu"])
    def test_x86(self, cpu_spec: str, image: Optional[str]):
        conf = self.prepare_conf(cpu_spec=cpu_spec, gpu_spec="H100", image=image)
        self.validate(conf)


class TestRenderRunSpecDiff:
    def test_diff(self):
        old = get_run_spec(
            run_name="test",
            repo_id="test-1",
            configuration_path="1.dstack.yml",
            profile=Profile(
                backends=[BackendType.AWS],
                regions=["us-west-1"],
                name="test",
                default=True,
            ),
            configuration=DevEnvironmentConfiguration(
                name="test",
                ide="vscode",
                inactivity_duration=60,
            ),
        )
        new = get_run_spec(
            run_name="test",
            repo_id="test-2",
            configuration_path="2.dstack.yml",
            profile=Profile(
                backends=[BackendType.AWS],
                regions=["us-west-2"],
                name="test",
                default=True,
            ),
            configuration=DevEnvironmentConfiguration(
                name="test",
                ide="cursor",
                inactivity_duration=None,
            ),
        )
        assert (
            render_run_spec_diff(old, new)
            == dedent(
                """
                - Repo ID
                - Configuration path
                - Configuration properties:
                  - ide
                  - inactivity_duration
                - Profile properties:
                  - regions
                """
            ).lstrip()
        )

    def test_field_type_change(self):
        old = get_run_spec(
            run_name="test",
            repo_id="test",
            profile=Profile(name="test"),
            configuration=DevEnvironmentConfiguration(
                name="test",
                ide="vscode",
            ),
        )
        new = get_run_spec(
            run_name="test",
            repo_id="test",
            profile=None,
            configuration=TaskConfiguration(
                name="test",
                commands=["sleep infinity"],
            ),
        )
        assert (
            render_run_spec_diff(old, new)
            == dedent(
                """
                - Configuration type
                - Profile
                """
            ).lstrip()
        )

    def test_no_diff(self):
        old = get_run_spec(run_name="test", repo_id="test")
        new = get_run_spec(run_name="test", repo_id="test")
        assert render_run_spec_diff(old, new) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestApplyStatusHelpers:
    async def test_waiting_for_requests_status_and_renderables(self, session):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            run_name="service-run",
            repo_id=repo.name,
            configuration=ServiceConfiguration(
                type="service",
                image="ubuntu:latest",
                commands=["echo hello"],
                port=80,
                replicas=Range[int](min=0, max=1),
                scaling=ScalingSpec(metric="rps", target=1),
            ),
        )
        run_model = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="service-run",
            run_spec=run_spec,
            status=RunStatus.PENDING,
        )
        run_model.service_spec = ServiceSpec(url="/proxy/services/test/service-run/").json()
        await session.commit()
        await session.refresh(run_model)

        api_run = Run(
            api_client=Mock(spec=APIClient, base_url="http://127.0.0.1:3000"),
            project=project.name,
            run=run_model_to_run(run_model),
        )

        assert _get_apply_status(api_run) == "[code]service-run[/] is waiting for requests..."
        assert _get_apply_wait_renderables(api_run) == [
            "Service URL: [link=http://127.0.0.1:3000/proxy/services/test/service-run/]http://127.0.0.1:3000/proxy/services/test/service-run/[/]"
        ]

    async def test_waiting_for_schedule_status_and_renderables(self, session):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run_model = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="scheduled-run",
            status=RunStatus.PENDING,
            next_triggered_at=datetime(2023, 1, 2, 3, 10, tzinfo=timezone.utc),
        )
        await session.refresh(run_model)

        api_run = Run(
            api_client=Mock(spec=APIClient),
            project=project.name,
            run=run_model_to_run(run_model),
        )
        next_run = datetime(2023, 1, 2, 3, 10, tzinfo=timezone.utc)
        api_run._run.next_triggered_at = next_run

        assert _get_apply_status(api_run) == "[code]scheduled-run[/] is waiting for schedule..."
        expected_next_run = next_run.astimezone().strftime("%Y-%m-%d %H:%M %Z")
        assert _get_apply_wait_renderables(api_run) == [f"Next run: {expected_next_run}"]
