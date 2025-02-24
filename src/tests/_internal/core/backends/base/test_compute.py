import re

from dstack._internal.core.backends.base.compute import (
    generate_unique_backend_name,
    generate_unique_gateway_instance_name,
    generate_unique_instance_name,
    generate_unique_volume_name,
)
from dstack._internal.server.testing.common import (
    get_gateway_compute_configuration,
    get_instance_configuration,
    get_volume,
)


class TestGenerateUniqueInstanceName:
    def test_generates_name(self):
        configuration = get_instance_configuration(
            project_name="project1", instance_name="my-instance"
        )
        name = generate_unique_instance_name(configuration, 60)
        assert re.match(r"^dstack-project1-my-instance-[a-z0-9]{8}$", name)


class TestGenerateUniqueGatewayInstanceName:
    def test_generates_name(self):
        configuration = get_gateway_compute_configuration(
            project_name="project1", instance_name="my-gateway"
        )
        name = generate_unique_gateway_instance_name(configuration, 60)
        assert re.match(r"^dstack-project1-my-gateway-[a-z0-9]{8}$", name)


class TestGenerateUniqueVolumeName:
    def test_generates_name(self):
        volume = get_volume(project_name="project1", name="my-volume")
        name = generate_unique_volume_name(volume, 60)
        assert re.match(r"^dstack-project1-my-volume-[a-z0-9]{8}$", name)


class TestGenerateUniqueBackendName:
    def test_generates_name_with_project(self):
        name = generate_unique_backend_name("instance", "project", 60)
        assert re.match(r"^dstack-project-instance-[a-z0-9]{8}$", name)

    def test_generates_name_without_project(self):
        name = generate_unique_backend_name("instance", None, 60)
        assert re.match(r"^dstack-instance-[a-z0-9]{8}$", name)

    def test_truncates_long_names(self):
        name = generate_unique_backend_name("a" * 100, "project", 30)
        assert re.match(r"^dstack-project-aaaaaa-[a-z0-9]{8}$", name)

    def test_validates_project_name(self):
        name = generate_unique_backend_name("instance", "invalid_project!@", 60)
        assert re.match(r"^dstack-instance-[a-z0-9]{8}$", name)
