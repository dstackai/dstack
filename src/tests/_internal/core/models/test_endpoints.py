import pytest

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.configurations import parse_apply_configuration
from dstack._internal.core.models.endpoints import EndpointConfiguration, EndpointPresetPolicy
from dstack._internal.core.models.profiles import CreationPolicy


class TestEndpointConfiguration:
    def test_parses_endpoint_configuration(self):
        conf = parse_apply_configuration(
            {
                "type": "endpoint",
                "name": "qwen-endpoint",
                "model": "Qwen/Qwen3-0.6B",
                "env": {"HF_TOKEN": "secret"},
                "fleets": ["gpu-fleet"],
                "creation_policy": "reuse",
                "preset_policy": "reuse",
            }
        )

        assert isinstance(conf, EndpointConfiguration)
        assert conf.name == "qwen-endpoint"
        assert conf.model == "Qwen/Qwen3-0.6B"
        assert conf.env.as_dict() == {"HF_TOKEN": "secret"}
        assert conf.fleets is not None
        fleet = conf.fleets[0]
        assert not isinstance(fleet, str)
        assert fleet.name == "gpu-fleet"
        assert conf.creation_policy == CreationPolicy.REUSE
        assert conf.preset_policy == EndpointPresetPolicy.REUSE

    def test_defaults_to_reuse_or_create_preset_policy(self):
        conf = EndpointConfiguration(name="qwen-endpoint", model="Qwen/Qwen3-0.6B")

        assert conf.preset_policy == EndpointPresetPolicy.REUSE_OR_CREATE

    def test_rejects_unknown_fields(self):
        with pytest.raises(ConfigurationError):
            parse_apply_configuration(
                {
                    "type": "endpoint",
                    "name": "qwen-endpoint",
                    "model": "Qwen/Qwen3-0.6B",
                    "commands": ["echo not supported"],
                }
            )
