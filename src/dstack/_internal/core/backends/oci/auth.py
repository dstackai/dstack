import oci
from typing_extensions import Any, Mapping

from dstack._internal.core.backends.oci.exceptions import any_oci_exception
from dstack._internal.core.backends.oci.models import AnyOCICreds, OCIDefaultCreds


def get_client_config(creds: AnyOCICreds) -> Mapping[str, Any]:
    if isinstance(creds, OCIDefaultCreds):
        return oci.config.from_file(file_location=creds.file, profile_name=creds.profile)
    return creds.dict(exclude={"type"})


def creds_valid(creds: AnyOCICreds) -> bool:
    try:
        config = get_client_config(creds)
        client = oci.identity.IdentityClient(config)
        client.get_tenancy(config["tenancy"])
    except any_oci_exception:
        return False
    return True
