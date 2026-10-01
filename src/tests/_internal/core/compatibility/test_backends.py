import json

from dstack._internal.core.backends.hotaisle.models import (
    HotAisleAPIKeyCreds,
    HotAisleBackendConfigWithCreds,
)
from dstack._internal.core.compatibility.backends import get_backend_config_excludes


def _request_body(config: HotAisleBackendConfigWithCreds) -> dict:
    return json.loads(config.model_dump_json(exclude=get_backend_config_excludes(config)))


class TestGetBackendConfigExcludes:
    def test_excludes_unset_hotaisle_bare_metal(self):
        config = HotAisleBackendConfigWithCreds(
            team_handle="test-team", creds=HotAisleAPIKeyCreds(api_key="test-key")
        )

        assert "bare_metal" not in _request_body(config)

    def test_keeps_set_hotaisle_bare_metal(self):
        config = HotAisleBackendConfigWithCreds(
            team_handle="test-team", creds=HotAisleAPIKeyCreds(api_key="test-key"), bare_metal=True
        )

        assert _request_body(config)["bare_metal"] is True
