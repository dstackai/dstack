import re
from typing import Any, Optional

import pytest

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.common import RegistryAuth
from dstack._internal.core.models.configurations import parse_run_configuration
from dstack._internal.core.models.resources import Range


class TestParseConfiguration:
    def test_services_replicas_and_scaling(self):
        def test_conf(replicas: Any, scaling: Optional[Any] = None):
            conf = {
                "type": "service",
                "commands": ["python3 -m http.server"],
                "port": 8000,
                "replicas": replicas,
            }
            if scaling:
                conf["scaling"] = scaling
            return conf

        assert parse_run_configuration(test_conf(1)).replicas == Range(min=1, max=1)
        assert parse_run_configuration(test_conf("2")).replicas == Range(min=2, max=2)
        assert parse_run_configuration(test_conf("3..3")).replicas == Range(min=3, max=3)
        with pytest.raises(
            ConfigurationError,
            match="When you set `replicas` to a range, ensure to specify `scaling`",
        ):
            parse_run_configuration(test_conf("0..10"))
        assert parse_run_configuration(
            test_conf(
                "0..10",
                {
                    "metric": "rps",
                    "target": 10,
                },
            )
        ).replicas == Range(min=0, max=10)
        with pytest.raises(
            ConfigurationError,
            match="When you set `replicas` to a range, ensure to specify `scaling`",
        ):
            parse_run_configuration(
                test_conf(
                    "0..10",
                    {
                        "metric": "rpc",
                        "target": 10,
                    },
                )
            )

    @pytest.mark.parametrize("shell", [None, "sh", "bash", "/usr/bin/zsh"])
    def test_shell_valid(self, shell: Optional[str]):
        conf = {
            "type": "task",
            "shell": shell,
            "commands": ["sleep inf"],
        }
        assert parse_run_configuration(conf).shell == shell

    def test_shell_invalid(self):
        conf = {
            "type": "task",
            "shell": "zsh",
            "commands": ["sleep inf"],
        }
        with pytest.raises(
            ConfigurationError, match="The value must be `sh`, `bash`, or an absolute path"
        ):
            parse_run_configuration(conf)

    @pytest.mark.parametrize(
        "python_version",
        [
            # Basic versions
            "3.9",
            "3.10.5",
            # Pre-releases
            "3.9a1",
            "3.10b2",
            "3.11rc1",
            # Post releases
            "3.9.0post1",
            # Development versions
            "3.10.dev0",
            # Local versions
            "3.9+local",
        ],
    )
    def test_python_version_valid(self, python_version: str):
        conf = {
            "type": "task",
            "python": python_version,
            "commands": ["python --version"],
        }
        parsed_conf = parse_run_configuration(conf)
        assert parsed_conf.python == python_version

    @pytest.mark.parametrize(
        "python_version",
        [
            "python3.9",
            "3.9.x",
            "",
            "latest",
            "stable",
        ],
    )
    def test_python_version_invalid(self, python_version: str):
        conf = {
            "type": "task",
            "python": python_version,
            "commands": ["python --version"],
        }
        with pytest.raises(
            ConfigurationError, match=f"Invalid Python version format: {re.escape(python_version)}"
        ):
            parse_run_configuration(conf)

    def test_python_version_float_conversion(self):
        # Test the special case where 3.10 becomes 3.10
        conf = {
            "type": "task",
            "python": 3.10,
            "commands": ["python --version"],
        }
        parsed_conf = parse_run_configuration(conf)
        assert parsed_conf.python == "3.10"

        # Test other float versions
        conf = {
            "type": "task",
            "python": 3.9,
            "commands": ["python --version"],
        }
        parsed_conf = parse_run_configuration(conf)
        assert parsed_conf.python == "3.9"

    def test_python_version_mutually_exclusive_with_image(self):
        conf = {
            "type": "task",
            "python": "3.9",
            "image": "python:3.9",
            "commands": ["python --version"],
        }
        with pytest.raises(
            ConfigurationError, match="`image` and `python` are mutually exclusive fields"
        ):
            parse_run_configuration(conf)

    def test_python_version_none(self):
        conf = {
            "type": "task",
            "python": None,
            "commands": ["echo hello"],
        }
        parsed_conf = parse_run_configuration(conf)
        assert parsed_conf.python is None

    def test_python_version_wrong_type(self):
        conf = {
            "type": "task",
            "python": ["3.9"],  # Wrong type - should be string
            "commands": ["python --version"],
        }
        with pytest.raises(
            ConfigurationError, match="Python version must be a string, got <class 'list'>"
        ):
            parse_run_configuration(conf)


def test_registry_auth_hashable():
    """
    RegistryAuth instances should be hashable
    to be used as cache keys in _get_image_config
    """
    registry_auth = RegistryAuth(username="username", password="password")
    hash(registry_auth)
