import pytest

from dstack._internal.utils.docker import (
    DockerImage,
    _is_host,
    parse_image_name,
    validate_image_name,
)


class TestParseImageName:
    @pytest.mark.parametrize(
        ["image", "expected"],
        [
            (
                "ubuntu:22.04",
                DockerImage(image="ubuntu", registry=None, repo="library/ubuntu", tag="22.04"),
            ),
            (
                "dstackai/miniforge:py3.9-0.2",
                DockerImage(
                    image="dstackai/miniforge",
                    registry=None,
                    repo="dstackai/miniforge",
                    tag="py3.9-0.2",
                ),
            ),
            (
                "ghcr.io/dstackai/miniforge",
                DockerImage(
                    image="ghcr.io/dstackai/miniforge",
                    registry="ghcr.io",
                    repo="dstackai/miniforge",
                    tag="latest",
                ),
            ),
            (
                "dstackai/miniforge@sha256:a4ba18a847a172a248d68faf6689e69fae4779b90b250211b79a26d21ddd6a15",
                DockerImage(
                    image="dstackai/miniforge",
                    registry=None,
                    repo="dstackai/miniforge",
                    tag="latest",
                    digest="sha256:a4ba18a847a172a248d68faf6689e69fae4779b90b250211b79a26d21ddd6a15",
                ),
            ),
        ],
    )
    def test_parse(self, image: str, expected: DockerImage) -> None:
        assert parse_image_name(image) == expected


class TestValidateImageName:
    @pytest.mark.parametrize(
        "image",
        [
            "ubuntu",
            "ubuntu:22.04",
            "dstackai/miniforge:py3.9-0.2",
            "ghcr.io/dstackai/miniforge",
            "localhost:5000/sshd:latest",
            "Registry.Example.com/team/sshd",
            "192.168.0.1:5000/sshd",
            "[::1]:5000/sshd",
            "my__org/ssh-d.server_1:v1.0_RC",
            "sshd@sha256:" + "0" * 64,
            "registry.example.com/sshd:1.0@sha512:" + "0" * 128,
        ],
    )
    def test_valid(self, image: str) -> None:
        validate_image_name(image)

    @pytest.mark.parametrize(
        ["image", "error"],
        [
            ("", "Invalid reference format"),
            (" ubuntu", "Invalid reference format"),
            ("Ubuntu", "Invalid reference format"),
            ("ghcr.io/dstackai/Miniforge", "Invalid reference format"),
            ("ubuntu:", "Invalid reference format"),
            ("ubuntu:.22.04", "Invalid reference format"),
            ("ubuntu:" + "1" * 129, "Invalid reference format"),
            ("-ubuntu", "Invalid reference format"),
            ("ubuntu//sshd", "Invalid reference format"),
            ("ubuntu@sha256", "Invalid reference format"),
            ("ubuntu@sha256:" + "0" * 31, "Invalid reference format"),
            ("ubuntu@md5:" + "0" * 32, "Unsupported digest algorithm: md5"),
            ("ubuntu@sha256:" + "0" * 63, "Invalid sha256 digest"),
            ("ubuntu@sha256:" + "A" * 64, "Invalid sha256 digest"),
        ],
    )
    def test_invalid(self, image: str, error: str) -> None:
        with pytest.raises(ValueError, match=error):
            validate_image_name(image)


class TestIsHost:
    @pytest.mark.parametrize(
        ["value", "expected"],
        [
            ("localhost", True),
            ("localhost:5000", True),
            ("ghcr.io", True),
            ("127.0.0.1", True),
            ("dstackai", False),
        ],
    )
    def test_is_host(self, value: str, expected: bool) -> None:
        assert _is_host(value) is expected
