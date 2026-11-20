"""Things stored in GatewayProxyRepo in addition to those from BaseProxyRepo."""

from typing import Optional

from pydantic import AnyHttpUrl

from dstack._internal.proxy.lib.const import DEFAULT_SERVICE_READ_TIMEOUT
from dstack._internal.proxy.lib.models import ImmutableModel


class ModelEntrypoint(ImmutableModel):
    project_name: str
    domain: str
    https: bool
    read_timeout: int = DEFAULT_SERVICE_READ_TIMEOUT


class ImportedModel(ImmutableModel):
    """A model that the importer project accesses through an export of the exporter project."""

    importer_project: str
    export_id: str
    """Metered with each request to the model, like `Service.id`."""
    exporter_project: str
    name: str
    """The model's name in the exporter project. With `exporter_project`,
    finds the model and its service."""


class ACMESettings(ImmutableModel):
    server: Optional[AnyHttpUrl] = None
    eab_kid: Optional[str] = None
    eab_hmac_key: Optional[str] = None


class GlobalProxyConfig(ImmutableModel):
    acme_settings: ACMESettings = ACMESettings()
