from typing import Optional

from dstack._internal.core.backends.base.configurator import BackendRecord
from dstack._internal.core.backends.digitalocean.backend import DigitalOceanBackend
from dstack._internal.core.backends.digitalocean_base.api_client import DigitalOceanAPIClient
from dstack._internal.core.backends.digitalocean_base.backend import BaseDigitalOceanBackend
from dstack._internal.core.backends.digitalocean_base.configurator import (
    BaseDigitalOceanConfigurator,
)
from dstack._internal.core.backends.digitalocean_base.models import (
    AnyBaseDigitalOceanCreds,
)
from dstack._internal.core.models.backends.base import (
    BackendType,
)


class DigitalOceanConfigurator(BaseDigitalOceanConfigurator):
    TYPE = BackendType.DIGITALOCEAN
    BACKEND_CLASS = DigitalOceanBackend
    API_URL = "https://api.digitalocean.com"

    def get_backend(self, record: BackendRecord) -> BaseDigitalOceanBackend:
        config = self._get_config(record)
        return DigitalOceanBackend(config=config, api_url=self.API_URL)

    def _validate_creds(self, creds: AnyBaseDigitalOceanCreds, project_name: Optional[str] = None):
        api_client = DigitalOceanAPIClient(creds.api_key, self.API_URL)
        api_client.validate_api_key()
        if project_name:
            api_client.validate_project_name(project_name)
