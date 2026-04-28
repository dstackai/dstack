import pytest

from dstack._internal.utils.docker import DockerImage, _is_host, parse_image_name


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
