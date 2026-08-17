import json
from typing import Any, Union
from unittest.mock import MagicMock, patch

import gpuhunt
import pytest

import dstack._internal.server.settings as server_settings
from dstack._internal.core.errors import DockerRegistryError
from dstack._internal.core.models.common import RegistryAuth, validate_extra_ignore
from dstack._internal.server.services import docker as docker_services
from dstack._internal.server.services.docker import (
    ImageConfigObject,
    ImageManifest,
    apply_server_docker_defaults,
    get_image_config_and_cpu_architectures,
    is_valid_docker_volume_target,
)


@pytest.fixture
def sample_image_manifest():
    # Source: https://github.com/opencontainers/image-spec/blob/main/manifest.md
    return {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {
            "mediaType": "application/vnd.oci.image.config.v1+json",
            "digest": "sha256:b5b2b2c507a0944348e0303114d8d93aaaa081732b86451d9bce1f432a537bc7",
            "size": 7023,
        },
        "layers": [
            {
                "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
                "digest": "sha256:9834876dcfb05cb167a5c24953eba58c4ac89b1adf57f28f2f9d09af107ee8f0",
                "size": 32654,
            },
            {
                "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
                "digest": "sha256:3c3a4604a545cdc127456d94e421cd355bca5b528f4a9c1905b15da2eb4a4c6b",
                "size": 16724,
            },
            {
                "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
                "digest": "sha256:ec4b8955958665577945c89419d1af06b5f7636b4ac3da7f12184802ad867736",
                "size": 73109,
            },
        ],
        "subject": {
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "digest": "sha256:5b0bcabd1ed22e9fb1310cf6c2dec7cdef19f0ad69efa1f392e94a4333501270",
            "size": 7682,
        },
        "annotations": {"com.example.key1": "value1", "com.example.key2": "value2"},
    }


@pytest.fixture
def sample_image_config_object():
    # Source: https://github.com/opencontainers/image-spec/blob/main/config.md
    return {
        "created": "2015-10-31T22:22:56.015925234Z",
        "author": "Alyssa P. Hacker <alyspdev@example.com>",
        "architecture": "amd64",
        "os": "linux",
        "config": {
            "User": "alice",
            "ExposedPorts": {"8080/tcp": {}},
            "Env": [
                "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "FOO=oci_is_a",
                "BAR=well_written_spec",
            ],
            "Entrypoint": ["/bin/my-app-binary"],
            "Cmd": ["--foreground", "--config", "/etc/my-app.d/default.cfg"],
            "Volumes": {"/var/job-result-data": {}, "/var/log/my-app-logs": {}},
            "WorkingDir": "/home/alice",
            "Labels": {
                "com.example.project.git.url": "https://example.com/project.git",
                "com.example.project.git.commit": "45a939b2999782a3f005621a8d0f29aa387e1d6b",
            },
        },
        "rootfs": {
            "diff_ids": [
                "sha256:c6f988f4874bb0add23a778f753c65efe992244e148a1d2ec2a8b664fb66bbd1",
                "sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef",
            ],
            "type": "layers",
        },
        "history": [
            {
                "created": "2015-10-31T22:22:54.690851953Z",
                "created_by": "/bin/sh -c #(nop) ADD file:a3bc1e842b69636f9df5256c49c5374fb4eef1e281fe3f282c65fb853ee171c5 in /",
            },
            {
                "created": "2015-10-31T22:22:55.613815829Z",
                "created_by": '/bin/sh -c #(nop) CMD ["sh"]',
                "empty_layer": True,
            },
            {
                "created": "2015-10-31T22:22:56.329850019Z",
                "created_by": "/bin/sh -c apk add curl",
            },
        ],
    }


def test_parse_image_manifest(sample_image_manifest):
    validate_extra_ignore(ImageManifest, sample_image_manifest)


def test_parse_image_config_object(sample_image_config_object):
    validate_extra_ignore(ImageConfigObject, sample_image_config_object)


def test_parse_image_config_object_with_config_null(sample_image_config_object):
    sample_image_config_object["config"] = None
    config_object = validate_extra_ignore(ImageConfigObject, sample_image_config_object)
    assert config_object.config is not None


@pytest.mark.parametrize(
    ["value", "expected"],
    [
        [None, None],
        ["", None],
        ["1000:1000", "1000:1000"],
    ],
)
def test_parse_image_config_object_user_field(sample_image_config_object, value, expected):
    sample_image_config_object["config"]["User"] = value
    config_object = validate_extra_ignore(ImageConfigObject, sample_image_config_object)
    assert config_object.config.user == expected


def test_parse_image_config_object_user_field_missing(sample_image_config_object):
    del sample_image_config_object["config"]["User"]
    config_object = validate_extra_ignore(ImageConfigObject, sample_image_config_object)
    assert config_object.config.user is None


@pytest.mark.parametrize(
    (
        "default_registry",
        "default_username",
        "default_password",
        "image_name",
        "input_auth",
        "expected_image",
        "expected_auth",
    ),
    [
        pytest.param(
            None,
            None,
            None,
            "python:3.12",
            None,
            "python:3.12",
            None,
            id="no-defaults-configured",
        ),
        pytest.param(
            "registry.example",
            None,
            None,
            "python:3.12",
            None,
            "registry.example/python:3.12",
            None,
            id="registry-prepended-no-credentials",
        ),
        pytest.param(
            "registry.example",
            "user",
            "pass",
            "python:3.12",
            None,
            "registry.example/python:3.12",
            RegistryAuth(username="user", password="pass"),
            id="registry-prepended-and-credentials-injected",
        ),
        pytest.param(
            "registry.example",
            "user",
            "pass",
            "python:3.12",
            RegistryAuth(username="run-user", password="run-pass"),
            "registry.example/python:3.12",
            RegistryAuth(username="run-user", password="run-pass"),
            id="registry-prepended-run-auth-preserved",
        ),
        pytest.param(
            None,
            "user",
            "pass",
            "python:3.12",
            None,
            "python:3.12",
            RegistryAuth(username="user", password="pass"),
            id="credentials-injected-without-default-registry",
        ),
        pytest.param(
            "registry.example",
            "user",
            "pass",
            "ghcr.io/org/image:tag",
            None,
            "ghcr.io/org/image:tag",
            None,
            id="image-with-registry-unchanged",
        ),
        pytest.param(
            None,
            "user",
            "pass",
            "ghcr.io/org/image:tag",
            None,
            "ghcr.io/org/image:tag",
            None,
            id="credentials-not-injected-when-image-has-registry",
        ),
    ],
)
def test_apply_server_docker_defaults(
    monkeypatch,
    default_registry,
    default_username,
    default_password,
    image_name,
    input_auth,
    expected_image,
    expected_auth,
):
    monkeypatch.setattr(server_settings, "SERVER_DEFAULT_DOCKER_REGISTRY", default_registry)
    monkeypatch.setattr(
        server_settings, "SERVER_DEFAULT_DOCKER_REGISTRY_USERNAME", default_username
    )
    monkeypatch.setattr(
        server_settings, "SERVER_DEFAULT_DOCKER_REGISTRY_PASSWORD", default_password
    )
    result_image, result_auth = apply_server_docker_defaults(image_name, input_auth)
    assert result_image == expected_image
    assert result_auth == expected_auth


class TestIsValidDockerVolumeTarget:
    @pytest.mark.parametrize(
        "path",
        [
            "/valid/path",
            "/valid-path_with.mixed123",
            "/valid_path",
            "/valid.path",
            "/valid-path",
            "/",
        ],
    )
    def test_valid_paths(self, path):
        assert is_valid_docker_volume_target(path)

    @pytest.mark.parametrize(
        "path",
        [
            "invalid/path",
            "",
            "relative/path",
            "./relative/path",
            "../relative/path",
        ],
    )
    def test_invalid_paths(self, path):
        assert not is_valid_docker_volume_target(path)

    def test_trailing_slash(self):
        assert not is_valid_docker_volume_target("/invalid/path/")


def _image_manifest(digest: str) -> str:
    return json.dumps({"config": {"digest": digest, "size": 7023}})


class TestGetImageConfigAndCpuArchitectures:
    """
    `get_manifest()` returns a dict of platform -> manifest JSON for an image index
    (multi-platform image) and a manifest JSON string for a single-platform image.
    """

    def _get_image_config(
        self,
        manifest_resp: Union[str, dict[str, str]],
        config_object: dict[str, Any],
    ) -> tuple[ImageConfigObject, set[gpuhunt.CPUArchitecture], MagicMock]:
        registry_client = MagicMock()
        registry_client.__enter__.return_value = registry_client
        registry_client.get_manifest.return_value = manifest_resp
        registry_client.pull_blob.return_value = [json.dumps(config_object).encode()]
        with patch.object(docker_services, "DXF", return_value=registry_client):
            image_config, cpu_architectures = get_image_config_and_cpu_architectures(
                "debian", None
            )
        return image_config, cpu_architectures, registry_client

    def test_index_reports_all_supported_architectures(self, sample_image_config_object):
        image_config, cpu_architectures, _ = self._get_image_config(
            {
                "linux/amd64": _image_manifest("sha256:amd64"),
                "linux/arm64": _image_manifest("sha256:arm64"),
            },
            sample_image_config_object,
        )

        assert cpu_architectures == {gpuhunt.CPUArchitecture.X86, gpuhunt.CPUArchitecture.ARM}
        assert image_config.config.user == "alice"

    def test_index_picks_the_x86_manifest_regardless_of_the_response_order(
        self, sample_image_config_object
    ):
        # The ImageConfigs are assumed to be the same for all images within the index, but the
        # manifest must still be picked deterministically, not in the registry response order
        _, _, registry_client = self._get_image_config(
            {
                "linux/arm64": _image_manifest("sha256:arm64"),
                "linux/amd64": _image_manifest("sha256:amd64"),
            },
            sample_image_config_object,
        )

        registry_client.pull_blob.assert_called_once_with("sha256:amd64")

    def test_index_falls_back_to_the_arm_manifest(self, sample_image_config_object):
        _, cpu_architectures, registry_client = self._get_image_config(
            {"linux/arm64": _image_manifest("sha256:arm64")},
            sample_image_config_object,
        )

        assert cpu_architectures == {gpuhunt.CPUArchitecture.ARM}
        registry_client.pull_blob.assert_called_once_with("sha256:arm64")

    def test_index_ignores_unsupported_platforms(self, sample_image_config_object):
        _, cpu_architectures, _ = self._get_image_config(
            {
                "linux/amd64": _image_manifest("sha256:amd64"),
                "linux/386": _image_manifest("sha256:386"),
                "linux/arm/v7": _image_manifest("sha256:armv7"),
                "windows/amd64": _image_manifest("sha256:windows"),
            },
            sample_image_config_object,
        )

        assert cpu_architectures == {gpuhunt.CPUArchitecture.X86}

    def test_rejects_index_without_supported_platforms(self, sample_image_config_object):
        with pytest.raises(DockerRegistryError, match="No supported OS/architectures found"):
            self._get_image_config(
                {
                    "linux/386": _image_manifest("sha256:386"),
                    "windows/amd64": _image_manifest("sha256:windows"),
                },
                sample_image_config_object,
            )

    @pytest.mark.parametrize(
        ["architecture", "expected_arch"],
        [
            ("amd64", gpuhunt.CPUArchitecture.X86),
            ("arm64", gpuhunt.CPUArchitecture.ARM),
        ],
    )
    def test_single_platform_image_uses_the_config_object_platform(
        self,
        sample_image_config_object,
        architecture: str,
        expected_arch: gpuhunt.CPUArchitecture,
    ):
        sample_image_config_object["architecture"] = architecture

        _, cpu_architectures, _ = self._get_image_config(
            _image_manifest("sha256:config"), sample_image_config_object
        )

        assert cpu_architectures == {expected_arch}

    @pytest.mark.parametrize(
        ["architecture", "os_name"],
        [
            ("386", "linux"),
            ("amd64", "windows"),
        ],
    )
    def test_rejects_single_platform_image_with_unsupported_platform(
        self, sample_image_config_object, architecture: str, os_name: str
    ):
        sample_image_config_object["architecture"] = architecture
        sample_image_config_object["os"] = os_name

        with pytest.raises(DockerRegistryError, match="No supported OS/architectures found"):
            self._get_image_config(_image_manifest("sha256:config"), sample_image_config_object)
