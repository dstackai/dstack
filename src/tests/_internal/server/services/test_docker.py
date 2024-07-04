import pytest

from dstack._internal.server.services.docker import (
    ImageConfigObject,
    ImageManifest,
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
    ImageManifest.__response__.parse_obj(sample_image_manifest)


def test_parse_image_config_object(sample_image_config_object):
    ImageConfigObject.__response__.parse_obj(sample_image_config_object)


def test_parse_image_config_object_with_config_null(sample_image_config_object):
    sample_image_config_object["config"] = None
    config_object = ImageConfigObject.__response__.parse_obj(sample_image_config_object)
    assert config_object.config is not None


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
