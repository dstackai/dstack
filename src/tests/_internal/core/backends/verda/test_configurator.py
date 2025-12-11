import sys
from unittest.mock import patch

import pytest

if sys.version_info < (3, 10):
    pytest.skip("Verda requires Python 3.10", allow_module_level=True)

from dstack._internal.core.backends.verda.configurator import (
    VerdaConfigurator,
)
from dstack._internal.core.backends.verda.models import (
    VerdaBackendConfigWithCreds,
    VerdaCreds,
)


class TestVerdaConfigurator:
    def test_validate_config_valid(self):
        config = VerdaBackendConfigWithCreds(
            type="verda",
            creds=VerdaCreds(client_id="valid", client_secret="valid"),
            regions=["FIN-01"],
        )
        with patch(
            "dstack._internal.core.backends.verda.configurator.VerdaConfigurator._validate_creds"
        ):
            VerdaConfigurator().validate_config(config, default_creds_enabled=True)
