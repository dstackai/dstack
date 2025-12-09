import sys
from unittest.mock import patch

import pytest

from dstack._internal.core.backends.verda.configurator import (
    VerdaConfigurator,
)
from dstack._internal.core.backends.verda.models import (
    VerdaBackendConfigWithCreds,
    VerdaCreds,
)


@pytest.mark.skipif(sys.version_info < (3, 10), reason="Verda requires Python 3.10")
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
