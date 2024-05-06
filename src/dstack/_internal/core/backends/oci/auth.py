import oci

from dstack._internal.core.backends.oci.exceptions import any_oci_exception
from dstack._internal.core.models.backends.oci import AnyOCICreds, OCIDefaultCreds


def creds_valid(creds: AnyOCICreds) -> bool:
    try:
        config = creds.to_client_config()
        client = oci.identity.IdentityClient(config)
        client.get_tenancy(config["tenancy"])
    except any_oci_exception:
        return False
    return True


def default_creds_available() -> bool:
    return creds_valid(OCIDefaultCreds())
