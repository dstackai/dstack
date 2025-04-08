from unittest.mock import patch

from dstack._internal.core.backends.datacrunch.configurator import (
    DataCrunchConfigurator,
)
from dstack._internal.core.backends.datacrunch.models import (
    DataCrunchBackendConfigWithCreds,
    DataCrunchCreds,
)


class TestDataCrunchConfigurator:
    def test_validate_config_valid(self):
        config = DataCrunchBackendConfigWithCreds(
            creds=DataCrunchCreds(client_id="valid", client_secret="valid"),
            regions=["FIN-01"],
        )
        with patch(
            "dstack._internal.core.backends.datacrunch.configurator.DataCrunchConfigurator._validate_creds"
        ):
            DataCrunchConfigurator().validate_config(config, default_creds_enabled=True)
