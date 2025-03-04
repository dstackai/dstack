from dstack._internal.core.models.backends.datacrunch import (
    DataCrunchConfigInfoWithCreds,
    DataCrunchCreds,
)
from dstack._internal.server.services.backends.configurators.datacrunch import (
    DataCrunchConfigurator,
)


class TestDataCrunchConfigurator:
    def test_validate_config_valid(self):
        config = DataCrunchConfigInfoWithCreds(
            creds=DataCrunchCreds(client_id="valid", client_secret="valid"),
            regions=["FIN-01"],
        )
        # Currently no validation is implemented
        DataCrunchConfigurator().validate_config(config)
