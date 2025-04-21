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


def test_registry_auth_hashable():
    """
    RegistryAuth instances should be hashable
    to be used as cache keys in _get_image_config
    """
    registry_auth = RegistryAuth(username="username", password="password")
    hash(registry_auth)
