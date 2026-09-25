from pathlib import Path
from typing import Dict, Optional

import oci
from typing_extensions import Any, Mapping

from dstack._internal.core.backends.oci.exceptions import any_oci_exception
from dstack._internal.core.backends.oci.models import AnyOCICreds, OCIDefaultCreds


def get_client_config(creds: AnyOCICreds) -> Mapping[str, Any]:
    if isinstance(creds, OCIDefaultCreds):
        return oci.config.from_file(file_location=creds.file, profile_name=creds.profile)
    return creds.model_dump(exclude={"type"})


def get_signer(config: Mapping[str, Any]) -> Optional[oci.signer.AbstractBaseSigner]:
    """
    Build a signer for a config that authenticates with a security token.

    `oci session authenticate` writes a profile holding a short-lived security token and
    an ephemeral key pair instead of a registered API key, so the API key signer the SDK
    builds by default cannot be used with such a profile. Returns None for API key
    profiles, letting the SDK build its default signer.
    """
    token_file = config.get("security_token_file")
    if not token_file:
        return None
    token = Path(token_file).expanduser().read_text().strip()
    private_key = oci.signer.load_private_key_from_file(
        Path(config["key_file"]).expanduser(), config.get("pass_phrase")
    )
    return oci.auth.signers.SecurityTokenSigner(token, private_key)


def make_client_kwargs(config: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Extra keyword arguments every OCI client must be constructed with for `config`.
    """
    signer = get_signer(config)
    return {"signer": signer} if signer is not None else {}


def creds_valid(creds: AnyOCICreds) -> bool:
    try:
        config = get_client_config(creds)
        client = oci.identity.IdentityClient(config, **make_client_kwargs(config))
        client.get_tenancy(config["tenancy"])
    except any_oci_exception:
        return False
    return True
